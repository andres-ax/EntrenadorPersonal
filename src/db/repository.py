"""Capa de persistencia. Todo SQL vive aqui (no en tools, no en handlers)."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.db.connection import async_session_factory
from src.db.models import (
    CheckinNocturno,
    Comida,
    Compromiso,
    CrisisLog,
    EjercicioRealizado,
    EscalacionState,
    EventoBot,
    FeedbackComida,
    MetricaCorporal,
    MetricaSueno,
    PersonalRecord,
    PlanSuscripcion,
    SesionEntrenamiento,
    Streak,
    Suscripcion,
    TipoAccionEscalacion,
    TipoComida,
    TipoCompromiso,
    TipoEjercicio,
    TipoStreak,
    TonoCoach,
    Usuario,
)


async def _get_usuario_id(session, telegram_id: int) -> Optional[int]:
    result = await session.execute(
        select(Usuario.id).where(Usuario.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


# --- Usuario ---


async def obtener_o_crear_usuario(telegram_id: int, nombre: str = "") -> Usuario:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        usuario = result.scalar_one_or_none()
        if usuario is None:
            usuario = Usuario(telegram_id=telegram_id, nombre=nombre)
            session.add(usuario)
            await session.commit()
            await session.refresh(usuario)
        elif nombre and not usuario.nombre:
            usuario.nombre = nombre
            await session.commit()
            await session.refresh(usuario)
        return usuario


async def obtener_usuario(telegram_id: int) -> Optional[Usuario]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


async def eliminar_usuario(telegram_id: int) -> bool:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        usuario = result.scalar_one_or_none()
        if usuario is None:
            return False
        await session.delete(usuario)
        await session.commit()
        return True


async def actualizar_usuario(telegram_id: int, **kwargs) -> Optional[Usuario]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        usuario = result.scalar_one_or_none()
        if usuario is None:
            return None
        for key, value in kwargs.items():
            if hasattr(usuario, key):
                setattr(usuario, key, value)
        await session.commit()
        await session.refresh(usuario)
        return usuario


async def marcar_bot_bloqueado(telegram_id: int, bloqueado: bool = True) -> None:
    """Se llama cuando el bot recibe Forbidden de Telegram (user lo bloqueo)."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        usuario = result.scalar_one_or_none()
        if usuario is not None:
            usuario.bot_bloqueado = bloqueado
            await session.commit()


async def listar_usuarios_activos() -> list[Usuario]:
    """Usuarios con onboarding completo y bot no bloqueado y no pausados hoy."""
    hoy = date.today()
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(
                Usuario.onboarding_completo == True,  # noqa: E712
                Usuario.bot_bloqueado == False,  # noqa: E712
            )
        )
        usuarios = list(result.scalars().all())
        return [u for u in usuarios if u.pausado_hasta is None or u.pausado_hasta < hoy]


# --- Sesiones de Entrenamiento ---


async def guardar_sesion(
    telegram_id: int,
    fecha_str: str,
    tipo: str,
    ejercicios: list[dict],
    duracion_min: int,
    rpe: Optional[float] = None,
    notas: str = "",
) -> SesionEntrenamiento:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            usuario = Usuario(telegram_id=telegram_id)
            session.add(usuario)
            await session.flush()
            uid = usuario.id

        sesion_entreno = SesionEntrenamiento(
            usuario_id=uid,
            fecha=date.fromisoformat(fecha_str),
            tipo=TipoEjercicio(tipo),
            duracion_min=duracion_min,
            rpe_promedio=rpe,
            notas=notas,
        )
        session.add(sesion_entreno)
        await session.flush()

        for ej in ejercicios:
            ejercicio = EjercicioRealizado(
                sesion_id=sesion_entreno.id,
                nombre=ej.get("nombre", ""),
                series=ej.get("series"),
                reps=ej.get("reps"),
                peso_kg=ej.get("peso_kg"),
                rpe=ej.get("rpe"),
            )
            session.add(ejercicio)

        await session.commit()
        await session.refresh(sesion_entreno, ["ejercicios"])
        return sesion_entreno


async def obtener_ultimas_sesiones(
    telegram_id: int, limite: int = 10
) -> list[SesionEntrenamiento]:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return []
        result = await session.execute(
            select(SesionEntrenamiento)
            .options(selectinload(SesionEntrenamiento.ejercicios))
            .where(SesionEntrenamiento.usuario_id == uid)
            .order_by(SesionEntrenamiento.fecha.desc())
            .limit(limite)
        )
        return list(result.scalars().all())


# --- Personal Records ---


async def obtener_pr_ejercicio(
    telegram_id: int, ejercicio: str
) -> Optional[PersonalRecord]:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return None
        result = await session.execute(
            select(PersonalRecord)
            .where(
                PersonalRecord.usuario_id == uid,
                PersonalRecord.ejercicio == ejercicio,
            )
            .order_by(PersonalRecord.peso_kg.desc(), PersonalRecord.reps.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def guardar_pr(
    telegram_id: int,
    ejercicio: str,
    peso_kg: float,
    reps: int,
    fecha: Optional[date] = None,
) -> PersonalRecord:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            usuario = Usuario(telegram_id=telegram_id)
            session.add(usuario)
            await session.flush()
            uid = usuario.id

        pr = PersonalRecord(
            usuario_id=uid,
            ejercicio=ejercicio,
            peso_kg=peso_kg,
            reps=reps,
            fecha=fecha or date.today(),
        )
        session.add(pr)
        await session.commit()
        await session.refresh(pr)
        return pr


async def listar_prs(telegram_id: int) -> list[PersonalRecord]:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return []
        result = await session.execute(
            select(PersonalRecord)
            .where(PersonalRecord.usuario_id == uid)
            .order_by(PersonalRecord.ejercicio, PersonalRecord.peso_kg.desc())
        )
        return list(result.scalars().all())


# --- Metricas Corporales ---


async def guardar_metrica_corporal(
    telegram_id: int,
    peso_kg: float,
    grasa_pct: Optional[float] = None,
    cintura_cm: Optional[float] = None,
) -> MetricaCorporal:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            usuario = Usuario(telegram_id=telegram_id)
            session.add(usuario)
            await session.flush()
            uid = usuario.id

        metrica = MetricaCorporal(
            usuario_id=uid,
            fecha=date.today(),
            peso_kg=peso_kg,
            grasa_pct=grasa_pct,
            cintura_cm=cintura_cm,
        )
        session.add(metrica)
        await session.commit()
        await session.refresh(metrica)
        return metrica


async def historial_peso(telegram_id: int, limit: int = 10) -> list[MetricaCorporal]:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return []
        result = await session.execute(
            select(MetricaCorporal)
            .where(MetricaCorporal.usuario_id == uid)
            .order_by(MetricaCorporal.fecha.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


# --- Comidas ---


async def guardar_comida(
    telegram_id: int,
    fecha_str: str,
    tipo: str,
    alimentos: list[str],
    calorias: int = 0,
    proteinas: float = 0,
    carbs: float = 0,
    grasas: float = 0,
) -> Comida:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            usuario = Usuario(telegram_id=telegram_id)
            session.add(usuario)
            await session.flush()
            uid = usuario.id

        comida = Comida(
            usuario_id=uid,
            fecha=date.fromisoformat(fecha_str),
            tipo=TipoComida(tipo),
            alimentos=json.dumps(alimentos, ensure_ascii=False),
            calorias=calorias,
            proteinas_g=proteinas,
            carbohidratos_g=carbs,
            grasas_g=grasas,
        )
        session.add(comida)
        await session.commit()
        await session.refresh(comida)
        return comida


async def resumen_nutricional_dia(
    telegram_id: int, fecha: Optional[date] = None
) -> dict:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return {
                "total_calorias": 0,
                "total_proteinas": 0,
                "total_carbs": 0,
                "total_grasas": 0,
                "comidas": [],
            }

        fecha = fecha or date.today()
        result = await session.execute(
            select(Comida).where(Comida.usuario_id == uid, Comida.fecha == fecha)
        )
        comidas = list(result.scalars().all())
        return {
            "total_calorias": sum(c.calorias or 0 for c in comidas),
            "total_proteinas": sum(c.proteinas_g or 0 for c in comidas),
            "total_carbs": sum(c.carbohidratos_g or 0 for c in comidas),
            "total_grasas": sum(c.grasas_g or 0 for c in comidas),
            "comidas": [
                {
                    "tipo": c.tipo.value if c.tipo else "otro",
                    "alimentos": c.alimentos,
                    "calorias": c.calorias or 0,
                }
                for c in comidas
            ],
        }


# --- Sueno ---


async def guardar_sueno(
    telegram_id: int,
    fecha_str: str,
    horas: float,
    calidad: int,
    notas: str = "",
) -> MetricaSueno:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            usuario = Usuario(telegram_id=telegram_id)
            session.add(usuario)
            await session.flush()
            uid = usuario.id

        sueno = MetricaSueno(
            usuario_id=uid,
            fecha=date.fromisoformat(fecha_str),
            horas=horas,
            calidad=calidad,
            notas=notas,
        )
        session.add(sueno)
        await session.commit()
        await session.refresh(sueno)
        return sueno


async def _resumen_sueno_semanal_internal(session, uid: int) -> dict:
    inicio = date.today() - timedelta(days=7)
    result = await session.execute(
        select(MetricaSueno).where(
            MetricaSueno.usuario_id == uid,
            MetricaSueno.fecha >= inicio,
        )
    )
    registros = list(result.scalars().all())
    if not registros:
        return {"promedio_horas": 0, "promedio_calidad": 0, "dias_registrados": 0}
    return {
        "promedio_horas": round(sum(r.horas or 0 for r in registros) / len(registros), 1),
        "promedio_calidad": round(sum(r.calidad or 0 for r in registros) / len(registros), 1),
        "dias_registrados": len(registros),
    }


async def resumen_sueno_semanal(telegram_id: int) -> dict:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return {"promedio_horas": 0, "promedio_calidad": 0, "dias_registrados": 0}
        return await _resumen_sueno_semanal_internal(session, uid)


# --- Reportes ---


async def reporte_semanal(telegram_id: int) -> dict:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return {
                "dias_entrenados": 0,
                "volumen_total_kg": 0,
                "total_ejercicios": 0,
                "nuevos_prs": [],
                "sueno": {},
                "periodo": "",
            }

        inicio_semana = date.today() - timedelta(days=7)

        result = await session.execute(
            select(SesionEntrenamiento)
            .options(selectinload(SesionEntrenamiento.ejercicios))
            .where(
                SesionEntrenamiento.usuario_id == uid,
                SesionEntrenamiento.fecha >= inicio_semana,
            )
        )
        sesiones = list(result.scalars().all())

        volumen: float = 0
        total_ejercicios = 0
        for s in sesiones:
            for ej in s.ejercicios:
                total_ejercicios += 1
                if ej.peso_kg and ej.series and ej.reps:
                    volumen += ej.peso_kg * ej.series * ej.reps

        result_pr = await session.execute(
            select(PersonalRecord).where(
                PersonalRecord.usuario_id == uid,
                PersonalRecord.fecha >= inicio_semana,
            )
        )
        nuevos_prs = list(result_pr.scalars().all())

        sueno_data = await _resumen_sueno_semanal_internal(session, uid)

        return {
            "dias_entrenados": len(sesiones),
            "volumen_total_kg": volumen,
            "total_ejercicios": total_ejercicios,
            "nuevos_prs": [
                {"ejercicio": p.ejercicio, "peso_kg": p.peso_kg, "reps": p.reps}
                for p in nuevos_prs
            ],
            "sueno": sueno_data,
            "periodo": f"{inicio_semana.isoformat()} - {date.today().isoformat()}",
        }


# ============================================================================
# Coach Molesto v1 - nuevas tablas
# ============================================================================


# --- Compromisos ---


async def crear_compromiso(
    telegram_id: int,
    objetivo_texto: str,
    deadline: date,
    frecuencia_semanal: int = 3,
    tipo_compromiso: str = "general",
    stake_simbolico: str = "",
) -> Compromiso:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            raise ValueError(f"Usuario {telegram_id} no existe")

        await session.execute(
            select(Compromiso)
            .where(Compromiso.usuario_id == uid, Compromiso.activo == True)  # noqa: E712
        )
        existentes = (
            await session.execute(
                select(Compromiso).where(
                    Compromiso.usuario_id == uid,
                    Compromiso.activo == True,  # noqa: E712
                )
            )
        ).scalars().all()
        for c in existentes:
            c.activo = False

        compromiso = Compromiso(
            usuario_id=uid,
            objetivo_texto=objetivo_texto,
            deadline=deadline,
            frecuencia_semanal=frecuencia_semanal,
            tipo_compromiso=TipoCompromiso(tipo_compromiso),
            stake_simbolico=stake_simbolico,
            activo=True,
        )
        session.add(compromiso)
        await session.commit()
        await session.refresh(compromiso)
        return compromiso


async def obtener_compromiso_activo(telegram_id: int) -> Optional[Compromiso]:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return None
        result = await session.execute(
            select(Compromiso)
            .where(
                Compromiso.usuario_id == uid,
                Compromiso.activo == True,  # noqa: E712
            )
            .order_by(Compromiso.fecha_firma.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def incrementar_citado_compromiso(compromiso_id: int) -> None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Compromiso).where(Compromiso.id == compromiso_id)
        )
        c = result.scalar_one_or_none()
        if c:
            c.citado_veces = (c.citado_veces or 0) + 1
            await session.commit()


async def actualizar_pinned_message_compromiso(
    compromiso_id: int, pinned_message_id: int
) -> None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Compromiso).where(Compromiso.id == compromiso_id)
        )
        c = result.scalar_one_or_none()
        if c:
            c.pinned_message_id = pinned_message_id
            await session.commit()


# --- Escalacion state ---


async def obtener_o_crear_escalacion(
    telegram_id: int, tipo_accion: str = "entreno"
) -> EscalacionState:
    hoy = date.today()
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            raise ValueError(f"Usuario {telegram_id} no existe")
        result = await session.execute(
            select(EscalacionState).where(
                EscalacionState.usuario_id == uid,
                EscalacionState.fecha == hoy,
                EscalacionState.tipo_accion == TipoAccionEscalacion(tipo_accion),
            )
        )
        estado = result.scalar_one_or_none()
        if estado is None:
            estado = EscalacionState(
                usuario_id=uid,
                fecha=hoy,
                tipo_accion=TipoAccionEscalacion(tipo_accion),
                level=0,
                mensajes_enviados_hoy=0,
            )
            session.add(estado)
            await session.commit()
            await session.refresh(estado)
        return estado


async def avanzar_escalacion(
    telegram_id: int, tipo_accion: str, mensaje_id: Optional[int] = None
) -> EscalacionState:
    """Sube level +1, incrementa contador, persiste timestamp."""
    hoy = date.today()
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            raise ValueError(f"Usuario {telegram_id} no existe")
        result = await session.execute(
            select(EscalacionState).where(
                EscalacionState.usuario_id == uid,
                EscalacionState.fecha == hoy,
                EscalacionState.tipo_accion == TipoAccionEscalacion(tipo_accion),
            )
        )
        estado = result.scalar_one_or_none()
        if estado is None:
            estado = EscalacionState(
                usuario_id=uid,
                fecha=hoy,
                tipo_accion=TipoAccionEscalacion(tipo_accion),
                level=1,
                mensajes_enviados_hoy=1,
                ultimo_mensaje_id=mensaje_id,
                ultimo_envio=datetime.utcnow(),
            )
            session.add(estado)
        else:
            estado.level = min(estado.level + 1, 4)
            estado.mensajes_enviados_hoy = (estado.mensajes_enviados_hoy or 0) + 1
            estado.ultimo_envio = datetime.utcnow()
            if mensaje_id:
                estado.ultimo_mensaje_id = mensaje_id
        await session.commit()
        await session.refresh(estado)
        return estado


async def reset_escalacion(telegram_id: int, tipo_accion: Optional[str] = None) -> int:
    """Reset al level 0 (despues de que el user cumple). Devuelve N filas afectadas."""
    hoy = date.today()
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return 0
        query = select(EscalacionState).where(
            EscalacionState.usuario_id == uid,
            EscalacionState.fecha == hoy,
        )
        if tipo_accion:
            query = query.where(
                EscalacionState.tipo_accion == TipoAccionEscalacion(tipo_accion)
            )
        result = await session.execute(query)
        estados = list(result.scalars().all())
        for e in estados:
            e.level = 0
        await session.commit()
        return len(estados)


# --- Streaks ---


async def obtener_o_crear_streak(
    telegram_id: int, tipo_streak: str = "entreno"
) -> Streak:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            raise ValueError(f"Usuario {telegram_id} no existe")
        result = await session.execute(
            select(Streak).where(
                Streak.usuario_id == uid,
                Streak.tipo_streak == TipoStreak(tipo_streak),
            )
        )
        streak = result.scalar_one_or_none()
        if streak is None:
            streak = Streak(usuario_id=uid, tipo_streak=TipoStreak(tipo_streak))
            session.add(streak)
            await session.commit()
            await session.refresh(streak)
        return streak


async def incrementar_streak(telegram_id: int, tipo_streak: str = "entreno") -> Streak:
    """Si la ultima_fecha es ayer -> dias_actuales+=1. Si hoy -> no-op. Else reset a 1."""
    hoy = date.today()
    ayer = hoy - timedelta(days=1)
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            raise ValueError(f"Usuario {telegram_id} no existe")
        result = await session.execute(
            select(Streak).where(
                Streak.usuario_id == uid,
                Streak.tipo_streak == TipoStreak(tipo_streak),
            )
        )
        streak = result.scalar_one_or_none()
        if streak is None:
            streak = Streak(
                usuario_id=uid,
                tipo_streak=TipoStreak(tipo_streak),
                dias_actuales=1,
                max_historico=1,
                ultima_fecha=hoy,
            )
            session.add(streak)
        elif streak.ultima_fecha == hoy:
            pass
        elif streak.ultima_fecha == ayer:
            streak.dias_actuales = (streak.dias_actuales or 0) + 1
            streak.max_historico = max(streak.max_historico or 0, streak.dias_actuales)
            streak.ultima_fecha = hoy
        else:
            streak.dias_actuales = 1
            streak.ultima_fecha = hoy
        await session.commit()
        await session.refresh(streak)
        return streak


async def usar_freeze_streak(telegram_id: int, tipo_streak: str = "entreno") -> bool:
    """Consume 1 freeze para evitar romper el streak hoy. Devuelve True si OK."""
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return False
        result = await session.execute(
            select(Streak).where(
                Streak.usuario_id == uid,
                Streak.tipo_streak == TipoStreak(tipo_streak),
            )
        )
        streak = result.scalar_one_or_none()
        if not streak or (streak.freezes_disponibles or 0) <= 0:
            return False
        streak.freezes_disponibles -= 1
        streak.freezes_usados = (streak.freezes_usados or 0) + 1
        streak.ultima_fecha = date.today()
        await session.commit()
        return True


# --- Checkins nocturnos ---


async def guardar_checkin_nocturno(
    telegram_id: int, opcion_id: int, via: str = "poll"
) -> CheckinNocturno:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            raise ValueError(f"Usuario {telegram_id} no existe")
        checkin = CheckinNocturno(
            usuario_id=uid, opcion_id=opcion_id, respondido_via=via
        )
        session.add(checkin)
        await session.commit()
        await session.refresh(checkin)
        return checkin


# --- Eventos bot (audit) ---


async def log_evento(
    telegram_id: Optional[int], tipo_evento: str, payload: Optional[dict] = None
) -> None:
    async with async_session_factory() as session:
        uid = None
        if telegram_id is not None:
            uid = await _get_usuario_id(session, telegram_id)
        evento = EventoBot(
            usuario_id=uid,
            tipo_evento=tipo_evento,
            payload=payload or {},
        )
        session.add(evento)
        await session.commit()


async def ultimos_eventos(telegram_id: int, limit: int = 3) -> list[EventoBot]:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return []
        result = await session.execute(
            select(EventoBot)
            .where(EventoBot.usuario_id == uid)
            .order_by(EventoBot.creado_en.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


# --- Crisis log ---


async def log_crisis(
    telegram_id: int,
    nivel: int,
    keywords: list[str],
    mensaje_usuario: str,
    mensaje_enviado_id: Optional[int] = None,
    derivado_a: Optional[str] = None,
) -> CrisisLog:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            raise ValueError(f"Usuario {telegram_id} no existe")
        log = CrisisLog(
            usuario_id=uid,
            nivel=nivel,
            keywords_detectadas=keywords,
            mensaje_usuario=mensaje_usuario,
            mensaje_enviado_id=mensaje_enviado_id,
            derivado_a=derivado_a or "",
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)
        return log


# --- Feedback de comida (Vision) ---


async def guardar_feedback_comida(
    telegram_id: int,
    foto_file_id: str,
    alimentos: list[str],
    calorias: int,
    proteinas: float,
    carbs: float,
    grasas: float,
    feedback_texto: str,
) -> FeedbackComida:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            raise ValueError(f"Usuario {telegram_id} no existe")
        fb = FeedbackComida(
            usuario_id=uid,
            foto_file_id=foto_file_id,
            alimentos_detectados=alimentos,
            calorias_estimadas=calorias,
            proteinas_g=proteinas,
            carbs_g=carbs,
            grasas_g=grasas,
            feedback_texto=feedback_texto,
        )
        session.add(fb)
        await session.commit()
        await session.refresh(fb)
        return fb


async def contar_fotos_hoy(telegram_id: int) -> int:
    hoy = date.today()
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return 0
        result = await session.execute(
            select(func.count(FeedbackComida.id)).where(
                FeedbackComida.usuario_id == uid,
                FeedbackComida.fecha == hoy,
            )
        )
        return result.scalar() or 0


# --- Suscripciones (V2 Stars) ---


async def activar_suscripcion_pro(
    telegram_id: int,
    telegram_payment_charge_id: str,
    star_amount: int,
    dias: int = 30,
) -> Suscripcion:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            raise ValueError(f"Usuario {telegram_id} no existe")
        sus = Suscripcion(
            usuario_id=uid,
            plan=PlanSuscripcion.PRO,
            telegram_payment_charge_id=telegram_payment_charge_id,
            star_amount=star_amount,
            expira_en=datetime.utcnow() + timedelta(days=dias),
            activa=True,
        )
        session.add(sus)
        await session.commit()
        await session.refresh(sus)
        return sus


async def es_usuario_pro(telegram_id: int) -> bool:
    """Devuelve True si tiene suscripcion activa Pro no expirada."""
    ahora = datetime.utcnow()
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return False
        result = await session.execute(
            select(Suscripcion).where(
                Suscripcion.usuario_id == uid,
                Suscripcion.plan == PlanSuscripcion.PRO,
                Suscripcion.activa == True,  # noqa: E712
                Suscripcion.expira_en > ahora,
            )
        )
        return result.scalar_one_or_none() is not None


async def cambiar_tono(telegram_id: int, tono: str) -> Optional[Usuario]:
    return await actualizar_usuario(telegram_id, tono=TonoCoach(tono))


async def aceptar_modo_militar(telegram_id: int) -> Optional[Usuario]:
    return await actualizar_usuario(
        telegram_id, modo_militar_aceptado_en=datetime.utcnow()
    )


async def pausar_recordatorios(telegram_id: int, dias: int) -> Optional[Usuario]:
    hasta = date.today() + timedelta(days=dias)
    return await actualizar_usuario(telegram_id, pausado_hasta=hasta)


async def set_quiet_hours(
    telegram_id: int, inicio_hhmm: str, fin_hhmm: str
) -> Optional[Usuario]:
    from datetime import time as time_t

    h_inicio, m_inicio = map(int, inicio_hhmm.split(":"))
    h_fin, m_fin = map(int, fin_hhmm.split(":"))
    return await actualizar_usuario(
        telegram_id,
        quiet_hours_inicio=time_t(h_inicio, m_inicio),
        quiet_hours_fin=time_t(h_fin, m_fin),
    )
