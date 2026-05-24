"""Helpers para programar tareas de sistema y recordatorios en Redis."""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from src.config import settings
from src.db.models import Recordatorio
from src.tasks.audit import log_task_audit
from src.tasks.queue import schedule_task
from src.timezone_utils import fecha_hoy_usuario, zoneinfo_for

logger = logging.getLogger(__name__)


def _normalizar_dias(raw: str) -> tuple[int, ...]:
    if not raw:
        return ()
    out: list[int] = []
    for p in raw.split(","):
        p = p.strip()
        if p.isdigit():
            n = int(p)
            if 0 <= n <= 6 and n not in out:
                out.append(n)
    return tuple(out)


def _proxima_ocurrencia(
    rec: Recordatorio,
    desde: datetime | None = None,
) -> datetime | None:
    tz = zoneinfo_for(rec.tz)
    ahora = desde or datetime.now(tz)
    if rec.dias_semana:
        dias = _normalizar_dias(rec.dias_semana)
        if not dias:
            return None
        for offset in range(8):
            candidato = (ahora + timedelta(days=offset)).date()
            if candidato.weekday() not in dias:
                continue
            when = datetime.combine(candidato, rec.hora, tzinfo=tz)
            if when > ahora:
                return when
        return None
    fecha = rec.fecha_unica or (ahora.date() + timedelta(days=1))
    when = datetime.combine(fecha, rec.hora, tzinfo=tz)
    return when if when > ahora else None


async def schedule_recordatorio_task(rec: Recordatorio) -> str | None:
    """Programa recordatorio en Redis. Devuelve task_id."""
    if not settings.use_redis_task_queue:
        return None
    when = _proxima_ocurrencia(rec)
    if when is None:
        return None
    hoy = when.astimezone(ZoneInfo("UTC")).date()
    idem = f"recordatorio:{rec.id}:{hoy.isoformat()}:{rec.hora.strftime('%H%M')}"
    task_id = await schedule_task(
        task_type="recordatorio",
        telegram_id=rec.telegram_id,
        run_at=when,
        payload={
            "mensaje": rec.mensaje,
            "recordatorio_id": rec.id,
            "dias_semana": rec.dias_semana or "",
        },
        timezone_name=rec.tz or "America/Bogota",
        idempotency_key=idem,
        created_by="agent",
        recordatorio_id=rec.id,
    )
    if task_id:
        await log_task_audit(
            task_id=task_id,
            telegram_id=rec.telegram_id,
            task_type="recordatorio",
            action="scheduled",
            payload_snapshot={"recordatorio_id": rec.id, "run_at": when.isoformat()},
        )
    return task_id


async def schedule_digest_matutino(telegram_id: int, when: datetime | None = None) -> str | None:
    if not settings.use_redis_task_queue:
        return None
    tz = await _tz_for(telegram_id)
    run_at = when or datetime.now(tz)
    hoy = await fecha_hoy_usuario(telegram_id)
    idem = f"digest:{telegram_id}:{hoy.isoformat()}"
    return await schedule_task(
        task_type="digest_matutino",
        telegram_id=telegram_id,
        run_at=run_at,
        payload={},
        timezone_name=str(tz),
        idempotency_key=idem,
        created_by="system",
    )


async def schedule_escalacion(
    telegram_id: int,
    tipo_accion: str,
    level: int,
    offset_hours: float = 0,
    freq: int = 3,
    streak: int = 0,
) -> str | None:
    if not settings.use_redis_task_queue:
        return None
    tz = await _tz_for(telegram_id)
    run_at = datetime.now(tz) + timedelta(hours=offset_hours, seconds=1)
    hoy = await fecha_hoy_usuario(telegram_id)
    idem = f"escalacion:{telegram_id}:{tipo_accion}:{hoy.isoformat()}:L{level}"
    return await schedule_task(
        task_type="escalacion",
        telegram_id=telegram_id,
        run_at=run_at,
        payload={
            "tipo_accion": tipo_accion,
            "level": level,
            "freq": freq,
            "streak": streak,
        },
        timezone_name=str(tz),
        idempotency_key=idem,
        created_by="system",
    )


async def schedule_hidratacion(telegram_id: int, offset_minutes: int = 0) -> str | None:
    if not settings.use_redis_task_queue:
        return None
    tz = await _tz_for(telegram_id)
    run_at = datetime.now(tz) + timedelta(minutes=offset_minutes)
    hoy = await fecha_hoy_usuario(telegram_id)
    slot = run_at.strftime("%Y%m%d%H")
    idem = f"hidratacion:{telegram_id}:{hoy.isoformat()}:{slot}"
    return await schedule_task(
        task_type="hidratacion",
        telegram_id=telegram_id,
        run_at=run_at,
        payload={},
        timezone_name=str(tz),
        idempotency_key=idem,
        created_by="system",
    )


async def schedule_deporte_skill(telegram_id: int, when: datetime | None = None) -> str | None:
    if not settings.use_redis_task_queue:
        return None
    tz = await _tz_for(telegram_id)
    run_at = when or datetime.now(tz)
    hoy = await fecha_hoy_usuario(telegram_id)
    idem = f"deporte_skill:{telegram_id}:{hoy.isoformat()}"
    return await schedule_task(
        task_type="deporte_skill",
        telegram_id=telegram_id,
        run_at=run_at,
        payload={},
        timezone_name=str(tz),
        idempotency_key=idem,
        created_by="system",
    )


async def schedule_desafio_generar(when: datetime | None = None) -> str | None:
    if not settings.use_redis_task_queue:
        return None
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(settings.default_timezone)
    run_at = when or datetime.now(tz)
    hoy = run_at.date()
    idem = f"desafio_generar:{hoy.isoformat()}"
    return await schedule_task(
        task_type="desafio_generar",
        telegram_id=0,
        run_at=run_at,
        payload={"fecha": hoy.isoformat()},
        timezone_name=str(tz),
        idempotency_key=idem,
        created_by="system",
    )


async def schedule_desafio_aviso_usuario(
    telegram_id: int,
    fecha: date | None = None,
) -> str | None:
    if not settings.use_redis_task_queue:
        return None
    tz = await _tz_for(telegram_id)
    hoy = fecha or await fecha_hoy_usuario(telegram_id)
    parts = settings.desafios_hora_aviso.split(":")
    hora = time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
    run_at = datetime.combine(hoy, hora, tzinfo=tz)
    now = datetime.now(tz)
    if run_at <= now:
        run_at = now + timedelta(seconds=30)
    idem = f"desafio_aviso:{telegram_id}:{hoy.isoformat()}"
    return await schedule_task(
        task_type="desafio_aviso",
        telegram_id=telegram_id,
        run_at=run_at,
        payload={"fecha": hoy.isoformat()},
        timezone_name=str(tz),
        idempotency_key=idem,
        created_by="system",
    )


async def schedule_desafio_cierre(desafio_id: int, fecha: date) -> str | None:
    if not settings.use_redis_task_queue:
        return None
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(settings.default_timezone)
    run_at = datetime.combine(fecha, time(23, 55), tzinfo=tz)
    idem = f"desafio_cierre:{desafio_id}"
    return await schedule_task(
        task_type="desafio_cierre",
        telegram_id=0,
        run_at=run_at,
        payload={"desafio_id": desafio_id},
        timezone_name=str(tz),
        idempotency_key=idem,
        created_by="system",
    )


async def _tz_for(telegram_id: int) -> ZoneInfo:
    from src.timezone_utils import tz_usuario

    return await tz_usuario(telegram_id)
