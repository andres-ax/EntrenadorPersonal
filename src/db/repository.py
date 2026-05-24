"""Capa de persistencia. Todo SQL vive aqui (no en tools, no en handlers)."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

from src.db.connection import async_session_factory
from src.db.models import (
    Admin,
    CategoriaDeporte,
    CheckinNocturno,
    DeporteCatalogo,
    SubtipoSesion,
    TipoPR,
    Comida,
    Compromiso,
    CrisisLog,
    DuracionPago,
    EjercicioRealizado,
    EscalacionState,
    EstadoPago,
    EventoBot,
    FeedbackComida,
    MetodoPago,
    MetricaCorporal,
    MetricaSueno,
    PagoComprobante,
    LlmUsage,
    AuditoriaTurno,
    PersonalRecord,
    PlanDefinicion,
    PlanSuscripcion,
    Recordatorio,
    RolAdmin,
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
    UsuarioBloqueado,
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
    """Borra el Usuario (cascade elimina entrenos, comidas, PRs, etc.).

    Retorna True si existia y se borro, False si no existia.
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        usuario = result.scalar_one_or_none()
        if usuario is None:
            logger.info(
                "eliminar_usuario uid=%s: no existe, nada que borrar",
                telegram_id,
            )
            return False
        usuario_pk = usuario.id
        await session.delete(usuario)
        await session.commit()
    try:
        from src.cache import invalidar_perfil_cache

        await invalidar_perfil_cache(telegram_id)
    except Exception:
        logger.exception(
            "eliminar_usuario uid=%s: fallo invalidar cache perfil",
            telegram_id,
        )
    logger.info(
        "eliminar_usuario uid=%s usuario_id=%s borrado (cascade)",
        telegram_id,
        usuario_pk,
    )
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
    # Cualquier mutacion al perfil invalida el cache del bloque inyectado en
    # _build_prompt. Import inline para evitar ciclo handlers/repository.
    try:
        from src.cache import invalidar_perfil_cache

        await invalidar_perfil_cache(telegram_id)
    except Exception:
        logger.exception(
            "actualizar_usuario uid=%s: fallo invalidar cache perfil",
            telegram_id,
        )
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
    from src.timezone_utils import fecha_hoy_usuario_model

    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(
                Usuario.onboarding_completo == True,  # noqa: E712
                Usuario.bot_bloqueado == False,  # noqa: E712
            )
        )
        usuarios = list(result.scalars().all())
        return [
            u
            for u in usuarios
            if u.pausado_hasta is None
            or u.pausado_hasta < fecha_hoy_usuario_model(u)
        ]


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
    """Guarda sesion de entreno (fuerza, cardio, movilidad, deporte generico).

    Dedup: si hay sesion abierta del mismo dia + tipo creada hace <2h,
    UPDATE acumulando ejercicios y notas. INSERT nueva en caso contrario.
    """
    fecha_obj = date.fromisoformat(fecha_str)
    tipo_enum = TipoEjercicio(tipo)
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            usuario = Usuario(telegram_id=telegram_id)
            session.add(usuario)
            await session.flush()
            uid = usuario.id

        umbral = datetime.utcnow() - VENTANA_SESION_ABIERTA
        result = await session.execute(
            select(SesionEntrenamiento)
            .options(selectinload(SesionEntrenamiento.ejercicios))
            .where(
                SesionEntrenamiento.usuario_id == uid,
                SesionEntrenamiento.fecha == fecha_obj,
                SesionEntrenamiento.tipo == tipo_enum,
                SesionEntrenamiento.cerrada == False,  # noqa: E712
                SesionEntrenamiento.updated_at >= umbral,
            )
            .order_by(SesionEntrenamiento.updated_at.desc())
            .limit(1)
        )
        existente = result.scalar_one_or_none()
        if existente is not None:
            existente.duracion_min = max(existente.duracion_min or 0, duracion_min)
            if rpe is not None:
                existente.rpe_promedio = rpe
            if notas:
                prefix = (existente.notas + "\n[+] ") if existente.notas else ""
                existente.notas = f"{prefix}{notas}"
            for ej in ejercicios:
                nuevo_ej = EjercicioRealizado(
                    sesion_id=existente.id,
                    nombre=ej.get("nombre", ""),
                    series=ej.get("series"),
                    reps=ej.get("reps"),
                    peso_kg=ej.get("peso_kg"),
                    rpe=ej.get("rpe"),
                )
                session.add(nuevo_ej)
            existente.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(existente, ["ejercicios"])
            logger.info(
                "guardar_sesion UPDATE uid=%s sesion_id=%s tipo=%s ejercicios+=%d",
                telegram_id, existente.id, tipo, len(ejercicios),
            )
            return existente

        sesion_entreno = SesionEntrenamiento(
            usuario_id=uid,
            fecha=fecha_obj,
            tipo=tipo_enum,
            duracion_min=duracion_min,
            rpe_promedio=rpe,
            notas=notas,
            cerrada=False,
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
    await _auto_streak_safe(telegram_id, "entreno")
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
    await _auto_streak_safe(telegram_id, "peso")
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
    await _auto_streak_safe(telegram_id, "comida")
    return comida


def _alimentos_set(raw: Any) -> set[str]:
    """Normaliza alimentos a un set de strings lowercase para comparar.

    Acepta str (JSON), list[str] o list[dict].
    """
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            data = []
    else:
        data = raw or []
    out: set[str] = set()
    for item in data:
        if isinstance(item, str):
            s = item.strip().lower()
            if s:
                out.add(s)
        elif isinstance(item, dict):
            nombre = (
                item.get("nombre") or item.get("name") or item.get("alimento") or ""
            )
            if isinstance(nombre, str) and nombre.strip():
                out.add(nombre.strip().lower())
    return out


async def buscar_comida_similar(
    telegram_id: int,
    fecha_str: str,
    tipo: str,
    alimentos: list[str],
    umbral_solapamiento: float = 0.5,
) -> Optional[int]:
    """Busca una Comida del mismo dia + tipo cuyos alimentos solapen >=umbral.

    Devuelve el id de la primera coincidencia o None. Pensado para que
    `registrar_comida` rechace duplicados sin abortar conversaciones donde
    el usuario solo describe la misma comida de otra forma.

    El solapamiento se calcula como `len(a & b) / max(len(a), len(b))`.
    """
    nuevo = _alimentos_set(alimentos)
    if not nuevo:
        return None
    try:
        fecha = date.fromisoformat(fecha_str)
    except (ValueError, TypeError):
        return None
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return None
        try:
            tipo_enum = TipoComida(tipo)
        except ValueError:
            return None
        result = await session.execute(
            select(Comida).where(
                Comida.usuario_id == uid,
                Comida.fecha == fecha,
                Comida.tipo == tipo_enum,
            )
        )
        for c in result.scalars().all():
            existente = _alimentos_set(c.alimentos)
            if not existente:
                continue
            interseccion = nuevo & existente
            denom = max(len(nuevo), len(existente))
            if denom > 0 and (len(interseccion) / denom) >= umbral_solapamiento:
                return c.id
        return None


async def resumen_nutricional_dia(
    telegram_id: int, fecha: Optional[date] = None
) -> dict:
    """Resumen nutricional del dia filtrando comidas placeholder (kcal=0).

    Devuelve:
    - totales: solo de comidas con datos (calorias>0 o macros>0)
    - comidas: lista de TODAS las comidas (con flag implícito de datos via
      `calorias`); el coach decide cómo mencionarlas. Asi mantenemos
      compat con quienes mostraban la lista.
    """
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return {
                "total_calorias": 0,
                "total_proteinas": 0,
                "total_carbs": 0,
                "total_grasas": 0,
                "comidas_con_datos": 0,
                "comidas_totales": 0,
                "comidas": [],
            }

        fecha = fecha or date.today()
        result = await session.execute(
            select(Comida).where(Comida.usuario_id == uid, Comida.fecha == fecha)
        )
        comidas = list(result.scalars().all())
        con_datos = [c for c in comidas if _comida_tiene_datos(c)]
        return {
            "total_calorias": sum(c.calorias or 0 for c in con_datos),
            "total_proteinas": sum(c.proteinas_g or 0 for c in con_datos),
            "total_carbs": sum(c.carbohidratos_g or 0 for c in con_datos),
            "total_grasas": sum(c.grasas_g or 0 for c in con_datos),
            "comidas_con_datos": len(con_datos),
            "comidas_totales": len(comidas),
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
    await _auto_streak_safe(telegram_id, "sueno")
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


# --- Reportes ---


def _comida_tiene_datos(c: "Comida") -> bool:
    """True si la comida tiene al menos un macro o calorias > 0.

    Comidas con calorias=0 y todos los macros en 0 son "placeholders" que
    el coach registraba antes de la validacion dura; las excluimos de los
    reportes para no inflar conteos.
    """
    if (c.calorias or 0) > 0:
        return True
    macros = (c.proteinas_g or 0) + (c.carbohidratos_g or 0) + (c.grasas_g or 0)
    return macros > 0


_EMPTY_NUTRICION_HOY: dict = {
    "total_calorias": 0,
    "total_proteinas": 0,
    "total_carbs": 0,
    "total_grasas": 0,
    "comidas_con_datos": 0,
    "comidas_totales": 0,
}


async def reporte_semanal(telegram_id: int) -> dict:
    """Reporte semanal: entrenos + PRs + sueno + nutricion de hoy.

    Devuelve:
    - dias_unicos_entreno: COUNT(DISTINCT fecha) de sesiones de la semana.
      Es el campo "humano" para "N entrenos esta semana".
    - sesiones_registradas: COUNT(*) de filas en SesionEntrenamiento (puede
      ser mayor que dias_unicos_entreno si hay duplicados o multiples sesiones).
    - dias_entrenados: alias = dias_unicos_entreno (mantiene compat con miniapp
      y handlers que ya leen ese campo).
    - nutricion_hoy: solo cuenta comidas con datos (calorias>0 o macros>0).
      Tambien expone `comidas_totales` (incluye placeholder) por si el coach
      quiere mencionar diferencia.
    """
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return {
                "dias_unicos_entreno": 0,
                "sesiones_registradas": 0,
                "dias_entrenados": 0,
                "volumen_total_kg": 0,
                "total_ejercicios": 0,
                "nuevos_prs": [],
                "sueno": {},
                "nutricion_hoy": dict(_EMPTY_NUTRICION_HOY),
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

        hoy = date.today()
        result_comidas_hoy = await session.execute(
            select(Comida).where(Comida.usuario_id == uid, Comida.fecha == hoy)
        )
        comidas_hoy = list(result_comidas_hoy.scalars().all())
        comidas_con_datos = [c for c in comidas_hoy if _comida_tiene_datos(c)]
        nutricion_hoy = {
            "total_calorias": sum(c.calorias or 0 for c in comidas_con_datos),
            "total_proteinas": sum(c.proteinas_g or 0 for c in comidas_con_datos),
            "total_carbs": sum(c.carbohidratos_g or 0 for c in comidas_con_datos),
            "total_grasas": sum(c.grasas_g or 0 for c in comidas_con_datos),
            "comidas_con_datos": len(comidas_con_datos),
            "comidas_totales": len(comidas_hoy),
        }

        dias_unicos = len({s.fecha for s in sesiones if s.fecha is not None})

        return {
            "dias_unicos_entreno": dias_unicos,
            "sesiones_registradas": len(sesiones),
            # Alias para compatibilidad con miniapp / handlers viejos que leen
            # `dias_entrenados`. Apuntamos al nuevo conteo correcto.
            "dias_entrenados": dias_unicos,
            "volumen_total_kg": volumen,
            "total_ejercicios": total_ejercicios,
            "nuevos_prs": [
                {"ejercicio": p.ejercicio, "peso_kg": p.peso_kg, "reps": p.reps}
                for p in nuevos_prs
            ],
            "sueno": sueno_data,
            "nutricion_hoy": nutricion_hoy,
            "periodo": f"{inicio_semana.isoformat()} - {hoy.isoformat()}",
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
    try:
        from src.cache import invalidar_perfil_cache

        await invalidar_perfil_cache(telegram_id)
    except Exception:
        logger.exception(
            "crear_compromiso uid=%s: fallo invalidar cache perfil",
            telegram_id,
        )
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


# --- Escalacion state ---


async def obtener_o_crear_escalacion(
    telegram_id: int, tipo_accion: str = "entreno"
) -> EscalacionState:
    from src.timezone_utils import fecha_hoy_usuario

    hoy = await fecha_hoy_usuario(telegram_id)
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
    from src.timezone_utils import fecha_hoy_usuario

    hoy = await fecha_hoy_usuario(telegram_id)
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
    from src.timezone_utils import fecha_hoy_usuario

    hoy = await fecha_hoy_usuario(telegram_id)
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


async def _auto_streak_safe(telegram_id: int, tipo_streak: str) -> None:
    """Llama `incrementar_streak` sin tirar excepciones.

    Pensado para invocarse desde `guardar_sesion`/`guardar_sueno`/
    `guardar_comida` y mantener los contadores de streak al dia sin que
    el coach tenga que recordarlo en cada turno. Si falla (p. ej. usuario
    se borro justo despues), solo logueamos y seguimos: el registro
    principal ya esta hecho.
    """
    try:
        await incrementar_streak(telegram_id, tipo_streak)
    except Exception:
        logger.exception(
            "auto_streak: incrementar_streak fallo uid=%s tipo=%s",
            telegram_id,
            tipo_streak,
        )


async def log_evento(
    telegram_id: Optional[int], tipo_evento: str, payload: Optional[dict] = None
) -> None:
    async with async_session_factory() as session:
        uid = None
        if telegram_id is not None:
            uid = await _get_usuario_id(session, telegram_id)
        evento = EventoBot(
            usuario_id=uid,
            telegram_id=telegram_id,
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


PLAN_RANKING: dict[PlanSuscripcion, int] = {
    PlanSuscripcion.FREE: 0,
    PlanSuscripcion.STARTER: 1,
    PlanSuscripcion.PRO: 2,
    PlanSuscripcion.ELITE: 3,
    PlanSuscripcion.LIFETIME: 4,
}


async def _esta_bloqueado(session, usuario_id: int) -> bool:
    result = await session.execute(
        select(UsuarioBloqueado).where(UsuarioBloqueado.usuario_id == usuario_id)
    )
    return result.scalar_one_or_none() is not None


async def obtener_plan_actual(telegram_id: int) -> PlanSuscripcion:
    """Devuelve el plan vigente. Si esta bloqueado o expirado -> FREE."""
    ahora = datetime.utcnow()
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        usuario = result.scalar_one_or_none()
        if usuario is None:
            return PlanSuscripcion.FREE
        if await _esta_bloqueado(session, usuario.id):
            return PlanSuscripcion.FREE
        plan = usuario.plan_actual or PlanSuscripcion.FREE
        if plan == PlanSuscripcion.LIFETIME:
            return PlanSuscripcion.LIFETIME
        if plan == PlanSuscripcion.FREE:
            return PlanSuscripcion.FREE
        if usuario.plan_expira_en is not None and usuario.plan_expira_en < ahora:
            usuario.plan_actual = PlanSuscripcion.FREE
            usuario.plan_expira_en = None
            await session.commit()
            return PlanSuscripcion.FREE
        return plan


async def es_plan_minimo(
    telegram_id: int, tier_minimo: PlanSuscripcion
) -> bool:
    """True si el plan vigente cumple o supera el tier minimo."""
    actual = await obtener_plan_actual(telegram_id)
    return PLAN_RANKING.get(actual, 0) >= PLAN_RANKING.get(tier_minimo, 0)


async def es_usuario_pro(telegram_id: int) -> bool:
    """Backwards-compat. True si plan >= PRO (Pro, Elite o Lifetime)."""
    return await es_plan_minimo(telegram_id, PlanSuscripcion.PRO)


_FEATURE_CACHE: dict[str, tuple[float, dict]] = {}


def _dias_por_duracion(plan: PlanSuscripcion, duracion: DuracionPago) -> int:
    if plan == PlanSuscripcion.LIFETIME:
        return 36500
    if duracion == DuracionPago.LIFETIME:
        return 36500
    if duracion == DuracionPago.ANUAL:
        return 365
    return 30


async def activar_plan(
    telegram_id: int,
    plan: PlanSuscripcion,
    dias: int | None = None,
    duracion: DuracionPago = DuracionPago.MENSUAL,
    metodo: MetodoPago = MetodoPago.MANUAL_ADMIN,
    monto_cop: int | None = None,
    comprobante_id: int | None = None,
) -> Suscripcion:
    """Crea/extiende suscripcion + actualiza plan_actual + plan_expira_en."""
    dias_real = dias if dias is not None else _dias_por_duracion(plan, duracion)
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        usuario = result.scalar_one_or_none()
        if usuario is None:
            raise ValueError(f"Usuario {telegram_id} no existe")
        ahora = datetime.utcnow()
        base = usuario.plan_expira_en or ahora
        if base < ahora:
            base = ahora
        nueva_expira = (
            None if plan == PlanSuscripcion.LIFETIME else base + timedelta(days=dias_real)
        )
        usuario.plan_actual = plan
        usuario.plan_expira_en = nueva_expira
        sus = Suscripcion(
            usuario_id=usuario.id,
            plan=plan,
            metodo_pago=metodo,
            monto_cop=monto_cop,
            comprobante_id=comprobante_id,
            iniciada_en=ahora,
            expira_en=nueva_expira,
            activa=True,
        )
        session.add(sus)
        await session.commit()
        await session.refresh(sus)
        return sus


async def desactivar_plan(telegram_id: int) -> bool:
    """Revoca el plan actual (downgrade a FREE)."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        usuario = result.scalar_one_or_none()
        if usuario is None:
            return False
        usuario.plan_actual = PlanSuscripcion.FREE
        usuario.plan_expira_en = None
        await session.execute(
            select(Suscripcion).where(
                Suscripcion.usuario_id == usuario.id,
                Suscripcion.activa == True,  # noqa: E712
            )
        )
        await session.commit()
    _FEATURE_CACHE.clear()
    return True


async def activar_suscripcion_pro(
    telegram_id: int,
    telegram_payment_charge_id: str,
    star_amount: int,
    dias: int = 30,
) -> Suscripcion:
    """Backwards-compat: activa Pro via Telegram Stars."""
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            raise ValueError(f"Usuario {telegram_id} no existe")
        result = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        usuario = result.scalar_one()
        ahora = datetime.utcnow()
        base = usuario.plan_expira_en or ahora
        if base < ahora:
            base = ahora
        nueva_expira = base + timedelta(days=dias)
        usuario.plan_actual = PlanSuscripcion.PRO
        usuario.plan_expira_en = nueva_expira
        sus = Suscripcion(
            usuario_id=uid,
            plan=PlanSuscripcion.PRO,
            telegram_payment_charge_id=telegram_payment_charge_id,
            star_amount=star_amount,
            metodo_pago=MetodoPago.TELEGRAM_STARS,
            monto_cop=None,
            iniciada_en=ahora,
            expira_en=nueva_expira,
            activa=True,
        )
        session.add(sus)
        await session.commit()
        await session.refresh(sus)
        return sus


# --- Pagos por comprobante ---


async def guardar_comprobante(
    telegram_id: int,
    foto_file_id: str,
    foto_sha256: str,
    plan_solicitado: PlanSuscripcion,
    duracion: DuracionPago,
    monto_esperado_cop: int,
    dias_otorgados: int,
    vision_payload: dict,
    referido_codigo: Optional[str] = None,
) -> PagoComprobante:
    """Inserta nuevo comprobante con estado=pendiente_humano."""
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            raise ValueError(f"Usuario {telegram_id} no existe")
        monto_cop = int(vision_payload.get("monto_cop") or 0)
        tolerancia = 500
        monto_match = (
            monto_cop > 0
            and abs(monto_cop - monto_esperado_cop) <= tolerancia
        )
        metodo_str = (vision_payload.get("metodo") or "otro").lower()
        try:
            metodo_enum = MetodoPago(metodo_str)
        except ValueError:
            metodo_enum = MetodoPago.OTRO
        comp = PagoComprobante(
            usuario_id=uid,
            foto_file_id=foto_file_id,
            foto_sha256=foto_sha256,
            monto_cop=monto_cop,
            monto_extraido_raw=vision_payload.get("monto_extraido_raw", ""),
            monto_esperado_cop=monto_esperado_cop,
            monto_match=monto_match,
            referencia=vision_payload.get("referencia", ""),
            cuenta_origen=vision_payload.get("cuenta_origen", ""),
            cuenta_destino=vision_payload.get("cuenta_destino", ""),
            fecha_pago=vision_payload.get("fecha_pago"),
            hora_pago=vision_payload.get("hora_pago"),
            metodo=metodo_enum,
            plan_solicitado=plan_solicitado,
            duracion_solicitada=duracion,
            dias_otorgados=dias_otorgados,
            estado=EstadoPago.PENDIENTE_HUMANO,
            vision_payload=vision_payload.get("raw", {}),
            referido_codigo=referido_codigo,
        )
        session.add(comp)
        await session.commit()
        await session.refresh(comp)
        return comp


async def marcar_comprobante_duplicado(comp_id: int, razon: str) -> None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(PagoComprobante).where(PagoComprobante.id == comp_id)
        )
        comp = result.scalar_one_or_none()
        if comp:
            comp.estado = EstadoPago.DUPLICADO
            comp.motivo_rechazo = razon
            comp.revisado_en = datetime.utcnow()
            await session.commit()


async def obtener_comprobante(comp_id: int) -> Optional[PagoComprobante]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(PagoComprobante).where(PagoComprobante.id == comp_id)
        )
        return result.scalar_one_or_none()


async def aprobar_comprobante(
    comp_id: int, admin_email: str, notas: str = ""
) -> Optional[PagoComprobante]:
    """Aprueba un comprobante y activa el plan asociado."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(PagoComprobante).where(PagoComprobante.id == comp_id)
        )
        comp = result.scalar_one_or_none()
        if comp is None or comp.estado == EstadoPago.APROBADO:
            return None
        comp.estado = EstadoPago.APROBADO
        comp.revisado_por = admin_email
        comp.revisado_en = datetime.utcnow()
        if notas:
            comp.notas_admin = notas
        usuario_result = await session.execute(
            select(Usuario).where(Usuario.id == comp.usuario_id)
        )
        usuario = usuario_result.scalar_one()
        await session.commit()
        await session.refresh(comp)
    logger.info(
        "aprobar_comprobante comp_id=%s plan=%s monto=%s uid=%s admin=%s",
        comp.id,
        getattr(comp.plan_solicitado, "value", comp.plan_solicitado),
        comp.monto_cop,
        usuario.telegram_id,
        admin_email,
    )
    await activar_plan(
        telegram_id=usuario.telegram_id,
        plan=comp.plan_solicitado,
        dias=comp.dias_otorgados,
        duracion=comp.duracion_solicitada,
        metodo=comp.metodo,
        monto_cop=comp.monto_cop,
        comprobante_id=comp.id,
    )
    return comp


async def rechazar_comprobante(
    comp_id: int, admin_email: str, motivo: str, bloquear: bool = False
) -> Optional[PagoComprobante]:
    """Rechaza un comprobante, revoca activacion provisional, opcionalmente bloquea usuario."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(PagoComprobante).where(PagoComprobante.id == comp_id)
        )
        comp = result.scalar_one_or_none()
        if comp is None:
            return None
        comp.estado = EstadoPago.RECHAZADO
        comp.motivo_rechazo = motivo
        comp.revisado_por = admin_email
        comp.revisado_en = datetime.utcnow()
        usuario_result = await session.execute(
            select(Usuario).where(Usuario.id == comp.usuario_id)
        )
        usuario = usuario_result.scalar_one()
        await session.commit()
        await session.refresh(comp)
    logger.warning(
        "rechazar_comprobante comp_id=%s uid=%s admin=%s bloquear=%s motivo=%s",
        comp.id,
        usuario.telegram_id,
        admin_email,
        bloquear,
        motivo[:120],
    )
    other_pendientes = await listar_comprobantes_activos(usuario.telegram_id)
    if not other_pendientes:
        await desactivar_plan(usuario.telegram_id)
    if bloquear:
        await bloquear_usuario(usuario.telegram_id, admin_email, motivo)
    return comp


async def listar_comprobantes_activos(telegram_id: int) -> list[PagoComprobante]:
    """Comprobantes en estado pendiente_humano o aprobado del usuario."""
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return []
        result = await session.execute(
            select(PagoComprobante).where(
                PagoComprobante.usuario_id == uid,
                PagoComprobante.estado.in_(
                    [EstadoPago.PENDIENTE_HUMANO, EstadoPago.APROBADO]
                ),
            )
        )
        return list(result.scalars().all())


async def listar_comprobantes_admin(
    estado: Optional[EstadoPago] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[PagoComprobante]:
    async with async_session_factory() as session:
        query = select(PagoComprobante)
        if estado:
            query = query.where(PagoComprobante.estado == estado)
        query = query.order_by(PagoComprobante.creado_en.desc()).limit(limit).offset(offset)
        result = await session.execute(query)
        return list(result.scalars().all())


# --- Bloqueo de usuarios ---


async def bloquear_usuario(
    telegram_id: int, admin_email: str, motivo: str
) -> bool:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            logger.warning(
                "bloquear_usuario uid=%s: usuario no existe", telegram_id
            )
            return False
        existente = await session.execute(
            select(UsuarioBloqueado).where(UsuarioBloqueado.usuario_id == uid)
        )
        if existente.scalar_one_or_none() is not None:
            logger.info(
                "bloquear_usuario uid=%s: ya estaba bloqueado", telegram_id
            )
            return False
        bloqueo = UsuarioBloqueado(
            usuario_id=uid,
            motivo=motivo,
            bloqueado_por=admin_email,
        )
        session.add(bloqueo)
        await session.commit()
    _FEATURE_CACHE.clear()
    logger.warning(
        "bloquear_usuario uid=%s admin=%s motivo=%s",
        telegram_id,
        admin_email,
        motivo[:120],
    )
    return True


async def desbloquear_usuario(telegram_id: int) -> bool:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return False
        result = await session.execute(
            select(UsuarioBloqueado).where(UsuarioBloqueado.usuario_id == uid)
        )
        bloqueo = result.scalar_one_or_none()
        if bloqueo is None:
            return False
        await session.delete(bloqueo)
        await session.commit()
    _FEATURE_CACHE.clear()
    return True


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


# ============================================================================
# PR2 - Deporte catalog helpers
# ============================================================================


_CATALOG_CACHE: dict[str, str] = {}
_CATALOG_FULL_CACHE: dict[str, dict] = {}


async def cargar_catalog_en_cache() -> int:
    """Carga catalog de deportes a cache en memoria. Llamar al startup.

    Returns:
        Numero de deportes cargados.
    """
    global _CATALOG_CACHE, _CATALOG_FULL_CACHE
    async with async_session_factory() as session:
        result = await session.execute(
            select(DeporteCatalogo).where(DeporteCatalogo.activo == True)  # noqa: E712
        )
        deportes = list(result.scalars().all())
    _CATALOG_CACHE = {d.slug: d.categoria for d in deportes}
    _CATALOG_FULL_CACHE = {
        d.slug: {
            "slug": d.slug,
            "nombre_es": d.nombre_es,
            "nombre_en": d.nombre_en,
            "categoria": d.categoria,
            "vocabulario": d.vocabulario or [],
            "metricas": d.metricas or [],
            "spots_colombia": d.spots_colombia or [],
            "referentes_colombia": d.referentes_colombia or [],
            "escena_co": d.escena_co or "",
            "federacion": d.federacion or "",
        }
        for d in deportes
    }
    return len(deportes)


def get_categoria_deporte(deporte_slug: str | None) -> str:
    """Devuelve la categoria de un deporte (slug) desde cache.

    Si el slug no existe, devuelve 'indoor_fuerza' como fallback seguro
    (vocabulario de gimnasio aplica a la mayoria de cosas).
    """
    if not deporte_slug:
        return "indoor_fuerza"
    return _CATALOG_CACHE.get(deporte_slug.lower().strip(), "indoor_fuerza")


def get_deporte_info(deporte_slug: str | None) -> dict:
    """Devuelve metadata completa del deporte desde cache."""
    if not deporte_slug:
        return {}
    return _CATALOG_FULL_CACHE.get(deporte_slug.lower().strip(), {})


# ============================================================================
# PR3 - PersonalRecord polimorfico (truco/grado/tiempo/etc) + sesiones skill
# ============================================================================


async def guardar_pr_truco(
    telegram_id: int,
    deporte: str,
    nombre_truco: str,
    spot: str = "",
    video_url: str = "",
    notas: str = "",
    fecha: Optional[date] = None,
) -> PersonalRecord:
    """PR de truco aterrizado (skate/BMX/rollers/parkour). tipo_pr=TRUCO.

    Solo registrar PRIMERA vez que se aterriza el truco; repeticiones van en
    SesionEntrenamiento.
    """
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            usuario = Usuario(telegram_id=telegram_id)
            session.add(usuario)
            await session.flush()
            uid = usuario.id

        pr = PersonalRecord(
            usuario_id=uid,
            tipo_pr=TipoPR.TRUCO,
            ejercicio=nombre_truco,
            deporte=deporte,
            spot=spot or None,
            video_url=video_url or None,
            notas=notas or None,
            fecha=fecha or date.today(),
        )
        session.add(pr)
        await session.commit()
        await session.refresh(pr)
        return pr


async def guardar_pr_via_escalada(
    telegram_id: int,
    nombre_via: str,
    grado: str,
    spot: str,
    estilo: str = "redpoint",
    notas: str = "",
    fecha: Optional[date] = None,
) -> PersonalRecord:
    """PR de via/boulder escalada. tipo_pr=GRADO."""
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            usuario = Usuario(telegram_id=telegram_id)
            session.add(usuario)
            await session.flush()
            uid = usuario.id

        pr = PersonalRecord(
            usuario_id=uid,
            tipo_pr=TipoPR.GRADO,
            ejercicio=nombre_via,
            deporte="climbing",
            grado=grado,
            spot=spot,
            notas=f"estilo={estilo}; {notas}" if notas else f"estilo={estilo}",
            fecha=fecha or date.today(),
        )
        session.add(pr)
        await session.commit()
        await session.refresh(pr)
        return pr


async def guardar_pr_tiempo(
    telegram_id: int,
    nombre_prueba: str,
    tiempo_seg: float,
    distancia_m: Optional[float] = None,
    deporte: str = "running",
    fecha: Optional[date] = None,
) -> PersonalRecord:
    """PR de tiempo (running, natacion, ciclismo TT). tipo_pr=TIEMPO."""
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            usuario = Usuario(telegram_id=telegram_id)
            session.add(usuario)
            await session.flush()
            uid = usuario.id

        pr = PersonalRecord(
            usuario_id=uid,
            tipo_pr=TipoPR.TIEMPO,
            ejercicio=nombre_prueba,
            deporte=deporte,
            tiempo_seg=tiempo_seg,
            distancia_m=distancia_m,
            fecha=fecha or date.today(),
        )
        session.add(pr)
        await session.commit()
        await session.refresh(pr)
        return pr


VENTANA_SESION_ABIERTA = timedelta(hours=2)


async def guardar_sesion_skill(
    telegram_id: int,
    deporte: str,
    duracion_min: int,
    spot: str = "",
    foco_sesion: str = "",
    trucos_intentados: int = 0,
    trucos_aterrizados: int = 0,
    num_caidas: int = 0,
    sensacion_1_5: int = 3,
    co_riders: str = "",
    notas: str = "",
    fecha: Optional[date] = None,
) -> SesionEntrenamiento:
    """Sesion skill urbano (skate/BMX/rollers/parkour/escalada).

    Dedup: si hay una sesion abierta (`cerrada=False`) del mismo
    `usuario + fecha + deporte_slug` con `updated_at >= now - 2h`,
    hacemos UPDATE acumulando contadores y reemplazando duracion por
    max(actual, nueva). Si no hay, INSERT con `cerrada=False`.
    """
    from src.db.models import TipoEjercicio

    fecha_use = fecha or date.today()
    sensacion_norm = max(1, min(5, sensacion_1_5))

    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            usuario = Usuario(telegram_id=telegram_id)
            session.add(usuario)
            await session.flush()
            uid = usuario.id

        # Buscar sesion abierta reciente del mismo dia+deporte
        umbral = datetime.utcnow() - VENTANA_SESION_ABIERTA
        result = await session.execute(
            select(SesionEntrenamiento)
            .where(
                SesionEntrenamiento.usuario_id == uid,
                SesionEntrenamiento.fecha == fecha_use,
                SesionEntrenamiento.deporte_slug == deporte,
                SesionEntrenamiento.cerrada == False,  # noqa: E712
                SesionEntrenamiento.updated_at >= umbral,
            )
            .order_by(SesionEntrenamiento.updated_at.desc())
            .limit(1)
        )
        existente = result.scalar_one_or_none()

        if existente is not None:
            # UPDATE acumulando datos. NO sumamos duracion (sería incorrecto
            # tratar 3 mensajes del mismo entreno como 3*duracion); usamos
            # max() para tomar el valor mas alto reportado.
            existente.duracion_min = max(existente.duracion_min or 0, duracion_min)
            existente.trucos_intentados = (
                (existente.trucos_intentados or 0) + trucos_intentados
            )
            existente.trucos_aterrizados = (
                (existente.trucos_aterrizados or 0) + trucos_aterrizados
            )
            existente.num_caidas = (existente.num_caidas or 0) + num_caidas
            existente.sensacion_1_5 = sensacion_norm
            if foco_sesion:
                existente.foco_sesion = foco_sesion
            if spot:
                existente.spot = spot
            if co_riders:
                existente.co_riders = co_riders
            if notas:
                prefix = (existente.notas + "\n[+] ") if existente.notas else ""
                existente.notas = f"{prefix}{notas}"
            existente.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(existente)
            logger.info(
                "guardar_sesion_skill UPDATE uid=%s sesion_id=%s deporte=%s "
                "duracion=%d trucos+=%d caidas+=%d",
                telegram_id, existente.id, deporte,
                existente.duracion_min,
                trucos_intentados, num_caidas,
            )
            return existente

        # No hay sesion abierta: INSERT nueva, abierta.
        sesion = SesionEntrenamiento(
            usuario_id=uid,
            fecha=fecha_use,
            tipo=TipoEjercicio.DEPORTE,
            subtipo=SubtipoSesion.SKILL,
            duracion_min=duracion_min,
            spot=spot or None,
            deporte_slug=deporte,
            foco_sesion=foco_sesion or None,
            trucos_intentados=trucos_intentados,
            trucos_aterrizados=trucos_aterrizados,
            num_caidas=num_caidas,
            sensacion_1_5=sensacion_norm,
            co_riders=co_riders or None,
            notas=notas or None,
            cerrada=False,  # nace abierta para que mensajes posteriores la actualicen
        )
        session.add(sesion)
        await session.commit()
        await session.refresh(sesion)
    # Solo en INSERT real (no en UPDATE) incrementamos streak.
    await _auto_streak_safe(telegram_id, "entreno")
    logger.info(
        "guardar_sesion_skill INSERT uid=%s sesion_id=%s deporte=%s duracion=%d",
        telegram_id, sesion.id, deporte, duracion_min,
    )
    return sesion


async def cerrar_sesion_abierta(
    telegram_id: int, sesion_id: Optional[int] = None
) -> Optional[SesionEntrenamiento]:
    """Marca cerrada=True una sesion del usuario.

    Si `sesion_id` se pasa, cierra esa especificamente (validando ownership).
    Si es None, cierra la ultima sesion abierta del usuario hoy.

    Retorna la sesion cerrada o None si no habia ninguna.
    """
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return None
        if sesion_id is not None:
            result = await session.execute(
                select(SesionEntrenamiento).where(
                    SesionEntrenamiento.id == sesion_id,
                    SesionEntrenamiento.usuario_id == uid,
                )
            )
        else:
            result = await session.execute(
                select(SesionEntrenamiento)
                .where(
                    SesionEntrenamiento.usuario_id == uid,
                    SesionEntrenamiento.fecha == date.today(),
                    SesionEntrenamiento.cerrada == False,  # noqa: E712
                )
                .order_by(SesionEntrenamiento.updated_at.desc())
                .limit(1)
            )
        sesion = result.scalar_one_or_none()
        if sesion is None:
            return None
        if sesion.cerrada:
            return sesion
        sesion.cerrada = True
        sesion.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(sesion)
    logger.info(
        "cerrar_sesion_abierta uid=%s sesion_id=%s cerrada",
        telegram_id, sesion.id,
    )
    return sesion


async def obtener_ultima_sesion_skill(
    telegram_id: int,
    deporte: Optional[str] = None,
    fecha: Optional[date] = None,
) -> Optional[SesionEntrenamiento]:
    """Devuelve la ultima sesion skill del usuario en una fecha (hoy default).

    Si `deporte` se da, filtra por ese deporte. Sin filtro, devuelve la mas
    reciente de cualquier deporte. Util para que el coach consulte valores
    actuales antes de corregir (ver `editar_sesion_reciente`).
    """
    fecha_use = fecha or date.today()
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return None
        query = select(SesionEntrenamiento).where(
            SesionEntrenamiento.usuario_id == uid,
            SesionEntrenamiento.fecha == fecha_use,
            SesionEntrenamiento.subtipo == SubtipoSesion.SKILL,
        )
        if deporte:
            query = query.where(SesionEntrenamiento.deporte_slug == deporte)
        query = query.order_by(SesionEntrenamiento.updated_at.desc()).limit(1)
        result = await session.execute(query)
        return result.scalar_one_or_none()


# Campos que `actualizar_sesion_skill_set` puede sobrescribir. Lista
# explicita para evitar updates a columnas sensibles (usuario_id, fecha).
_CAMPOS_EDITABLES_SESION_SKILL = {
    "duracion_min",
    "trucos_intentados",
    "trucos_aterrizados",
    "num_caidas",
    "sensacion_1_5",
    "foco_sesion",
    "spot",
    "co_riders",
    "notas",
    "cerrada",
}


async def actualizar_sesion_skill_set(
    telegram_id: int,
    sesion_id: Optional[int] = None,
    deporte: Optional[str] = None,
    fecha: Optional[date] = None,
    **campos: Any,
) -> Optional[SesionEntrenamiento]:
    """SET (no SUM) de campos en una sesion skill del usuario.

    - Si `sesion_id` se da, busca esa fila exacta validando ownership.
    - Si no, busca la mas reciente del dia (hoy por default) + deporte
      opcional, INCLUSO si esta `cerrada`. Este es el camino "corregir
      lo que acabo de registrar".

    Solo aplica updates en sesiones del dia indicado (no editamos
    historico de dias anteriores para preservar reportes pasados).

    Solo procesa los campos presentes en `_CAMPOS_EDITABLES_SESION_SKILL`
    cuyos valores sean diferentes de None. Numeros se aceptan tal cual,
    strings se aceptan si son no-vacios.
    """
    fecha_use = fecha or date.today()
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            logger.warning(
                "actualizar_sesion_skill_set: usuario uid=%s no existe",
                telegram_id,
            )
            return None

        if sesion_id is not None and sesion_id > 0:
            result = await session.execute(
                select(SesionEntrenamiento).where(
                    SesionEntrenamiento.id == sesion_id,
                    SesionEntrenamiento.usuario_id == uid,
                )
            )
        else:
            query = select(SesionEntrenamiento).where(
                SesionEntrenamiento.usuario_id == uid,
                SesionEntrenamiento.fecha == fecha_use,
                SesionEntrenamiento.subtipo == SubtipoSesion.SKILL,
            )
            if deporte:
                query = query.where(
                    SesionEntrenamiento.deporte_slug == deporte
                )
            query = query.order_by(SesionEntrenamiento.updated_at.desc()).limit(1)
            result = await session.execute(query)
        sesion = result.scalar_one_or_none()
        if sesion is None:
            logger.info(
                "actualizar_sesion_skill_set uid=%s sin sesion (id=%s deporte=%s fecha=%s)",
                telegram_id, sesion_id, deporte, fecha_use,
            )
            return None
        # Restriccion: solo hoy. Para historico, requeriria flag explicito.
        if sesion.fecha != date.today():
            logger.warning(
                "actualizar_sesion_skill_set uid=%s sesion_id=%s rechazada "
                "(fecha=%s != hoy)",
                telegram_id, sesion.id, sesion.fecha,
            )
            return None

        antes: dict[str, Any] = {}
        despues: dict[str, Any] = {}
        for campo, valor in campos.items():
            if campo not in _CAMPOS_EDITABLES_SESION_SKILL:
                continue
            if valor is None:
                continue
            if isinstance(valor, str) and not valor.strip():
                continue
            antes[campo] = getattr(sesion, campo, None)
            despues[campo] = valor
            setattr(sesion, campo, valor)
        if not despues:
            logger.info(
                "actualizar_sesion_skill_set uid=%s sesion_id=%s sin cambios",
                telegram_id, sesion.id,
            )
            return sesion
        sesion.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(sesion)
    logger.info(
        "actualizar_sesion_skill_set uid=%s sesion_id=%s antes=%s despues=%s",
        telegram_id, sesion.id, antes, despues,
    )
    return sesion


async def obtener_comidas_dia(
    telegram_id: int, fecha: Optional[date] = None
) -> list[Comida]:
    """Lista las Comida de un usuario en una fecha (hoy default)."""
    fecha_use = fecha or date.today()
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return []
        result = await session.execute(
            select(Comida)
            .where(Comida.usuario_id == uid, Comida.fecha == fecha_use)
            .order_by(Comida.id.desc())
        )
        return list(result.scalars().all())


async def eliminar_comida(
    telegram_id: int,
    comida_id: Optional[int] = None,
    tipo: Optional[str] = None,
    fecha: Optional[date] = None,
) -> Optional[int]:
    """Borra UNA comida del usuario.

    - Si `comida_id` se da, valida ownership y borra esa fila.
    - Si no, busca por `tipo` (desayuno/almuerzo/cena/snack/post_entreno)
      en la `fecha` (hoy default) y borra la MAS RECIENTE de ese tipo.

    Retorna el id de la fila borrada o None si no encontro nada.
    Restringido a borrar comidas del dia actual (no historico).
    """
    fecha_use = fecha or date.today()
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return None
        if comida_id is not None and comida_id > 0:
            result = await session.execute(
                select(Comida).where(
                    Comida.id == comida_id,
                    Comida.usuario_id == uid,
                )
            )
            comida = result.scalar_one_or_none()
        else:
            if not tipo:
                logger.warning(
                    "eliminar_comida uid=%s: sin comida_id ni tipo",
                    telegram_id,
                )
                return None
            try:
                tipo_enum = TipoComida(tipo)
            except ValueError:
                logger.warning(
                    "eliminar_comida uid=%s: tipo invalido %s",
                    telegram_id, tipo,
                )
                return None
            result = await session.execute(
                select(Comida)
                .where(
                    Comida.usuario_id == uid,
                    Comida.fecha == fecha_use,
                    Comida.tipo == tipo_enum,
                )
                .order_by(Comida.id.desc())
                .limit(1)
            )
            comida = result.scalar_one_or_none()
        if comida is None:
            logger.info(
                "eliminar_comida uid=%s no encontro (id=%s tipo=%s fecha=%s)",
                telegram_id, comida_id, tipo, fecha_use,
            )
            return None
        if comida.fecha != date.today():
            logger.warning(
                "eliminar_comida uid=%s id=%s rechazado (fecha=%s != hoy)",
                telegram_id, comida.id, comida.fecha,
            )
            return None
        comida_id_borrada = comida.id
        await session.delete(comida)
        await session.commit()
    logger.info(
        "eliminar_comida uid=%s id=%s borrada (tipo=%s fecha=%s)",
        telegram_id, comida_id_borrada, tipo, fecha_use,
    )
    return comida_id_borrada


async def guardar_sesion_sparring(
    telegram_id: int,
    estilo: str,
    rounds: int,
    duracion_round_min: int = 3,
    intensidad_1_10: int = 5,
    golpe_cabeza_fuerte: bool = False,
    notas: str = "",
    fecha: Optional[date] = None,
) -> SesionEntrenamiento:
    """Sesion sparring (combate). subtipo=SPARRING."""
    from src.db.models import TipoEjercicio

    duracion_total = max(1, rounds * duracion_round_min)
    notas_finales = notas
    if golpe_cabeza_fuerte:
        notas_finales = (
            f"[GOLPE_CABEZA_FUERTE] {notas}" if notas else "[GOLPE_CABEZA_FUERTE]"
        )

    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            usuario = Usuario(telegram_id=telegram_id)
            session.add(usuario)
            await session.flush()
            uid = usuario.id

        sesion = SesionEntrenamiento(
            usuario_id=uid,
            fecha=fecha or date.today(),
            tipo=TipoEjercicio.DEPORTE,
            subtipo=SubtipoSesion.SPARRING,
            duracion_min=duracion_total,
            rounds=rounds,
            intensidad_1_10=max(1, min(10, intensidad_1_10)),
            deporte_slug=estilo,
            notas=notas_finales,
        )
        session.add(sesion)
        await session.commit()
        await session.refresh(sesion)
        return sesion


async def listar_sesiones_skill(
    telegram_id: int, deporte: str, dias: int = 30
) -> list[SesionEntrenamiento]:
    """Lista sesiones skill de un deporte en ventana de N dias."""
    desde = date.today() - timedelta(days=dias)
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return []
        result = await session.execute(
            select(SesionEntrenamiento).where(
                SesionEntrenamiento.usuario_id == uid,
                SesionEntrenamiento.subtipo == SubtipoSesion.SKILL,
                SesionEntrenamiento.deporte_slug == deporte,
                SesionEntrenamiento.fecha >= desde,
            ).order_by(SesionEntrenamiento.fecha.desc())
        )
        return list(result.scalars().all())


async def listar_trucos_aterrizados(
    telegram_id: int, deporte: Optional[str] = None
) -> list[PersonalRecord]:
    """Lista todos los PRs tipo TRUCO del usuario."""
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return []
        query = select(PersonalRecord).where(
            PersonalRecord.usuario_id == uid,
            PersonalRecord.tipo_pr == TipoPR.TRUCO,
        )
        if deporte:
            query = query.where(PersonalRecord.deporte == deporte)
        query = query.order_by(PersonalRecord.fecha.desc())
        result = await session.execute(query)
        return list(result.scalars().all())


async def listar_sparring_reciente(
    telegram_id: int, dias: int = 14
) -> list[SesionEntrenamiento]:
    """Sesiones sparring recientes (para detectar trauma craneal acumulado)."""
    desde = date.today() - timedelta(days=dias)
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return []
        result = await session.execute(
            select(SesionEntrenamiento).where(
                SesionEntrenamiento.usuario_id == uid,
                SesionEntrenamiento.subtipo == SubtipoSesion.SPARRING,
                SesionEntrenamiento.fecha >= desde,
            ).order_by(SesionEntrenamiento.fecha.desc())
        )
        return list(result.scalars().all())


# --- Recordatorios personalizados ---


async def crear_recordatorio(
    telegram_id: int,
    mensaje: str,
    hora: time,
    dias_semana: str = "",
    fecha_unica: Optional[date] = None,
    tz: Optional[str] = None,
) -> Optional[Recordatorio]:
    """Crea o reactiva recordatorio one-shot/recurrente (dedup activos)."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        usuario = result.scalar_one_or_none()
        if usuario is None:
            return None
        msg_norm = mensaje[:500].strip()
        existente = await session.execute(
            select(Recordatorio).where(
                Recordatorio.usuario_id == usuario.id,
                Recordatorio.hora == hora,
                Recordatorio.mensaje == msg_norm,
                Recordatorio.activo.is_(True),
            )
        )
        prev = existente.scalar_one_or_none()
        if prev is not None:
            prev.dias_semana = (dias_semana or "").strip()
            prev.fecha_unica = fecha_unica
            prev.tz = tz or usuario.timezone or "America/Bogota"
            await session.commit()
            await session.refresh(prev)
            return prev
        rec = Recordatorio(
            usuario_id=usuario.id,
            telegram_id=telegram_id,
            mensaje=msg_norm,
            hora=hora,
            dias_semana=(dias_semana or "").strip(),
            fecha_unica=fecha_unica,
            tz=tz or usuario.timezone or "America/Bogota",
            activo=True,
        )
        session.add(rec)
        await session.commit()
        await session.refresh(rec)
        return rec


async def count_auditoria_reciente(telegram_id: int, dias: int = 14) -> int:
    """Turnos de auditoría en los últimos N días (actividad conversacional)."""
    from src.db.models import AuditoriaTurno

    desde = datetime.utcnow() - timedelta(days=dias)
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count(AuditoriaTurno.id)).where(
                AuditoriaTurno.telegram_id == telegram_id,
                AuditoriaTurno.creado_en >= desde,
            )
        )
        return int(result.scalar() or 0)


async def listar_recordatorios(
    telegram_id: int, solo_activos: bool = True
) -> list[Recordatorio]:
    """Lista recordatorios del usuario (activos por defecto)."""
    async with async_session_factory() as session:
        query = select(Recordatorio).where(Recordatorio.telegram_id == telegram_id)
        if solo_activos:
            query = query.where(Recordatorio.activo.is_(True))
        query = query.order_by(Recordatorio.hora.asc(), Recordatorio.id.asc())
        result = await session.execute(query)
        return list(result.scalars().all())


async def listar_recordatorios_activos_global() -> list[Recordatorio]:
    """Todos los recordatorios activos del sistema. Uso: scheduler loader al boot."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Recordatorio).where(Recordatorio.activo.is_(True))
        )
        return list(result.scalars().all())


async def desactivar_recordatorio(recordatorio_id: int, telegram_id: int) -> bool:
    """Marca el recordatorio como inactivo. Verifica ownership via telegram_id."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Recordatorio).where(
                Recordatorio.id == recordatorio_id,
                Recordatorio.telegram_id == telegram_id,
            )
        )
        rec = result.scalar_one_or_none()
        if rec is None:
            return False
        rec.activo = False
        await session.commit()
        return True


async def marcar_recordatorio_enviado(recordatorio_id: int) -> Recordatorio | None:
    """Actualiza `ultimo_envio` y, si es one-shot, lo desactiva. Devuelve el modelo."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Recordatorio).where(Recordatorio.id == recordatorio_id)
        )
        rec = result.scalar_one_or_none()
        if rec is None:
            return None
        rec.ultimo_envio = datetime.utcnow()
        if rec.fecha_unica is not None and not rec.dias_semana:
            rec.activo = False
        await session.commit()
        await session.refresh(rec)
        return rec


# ============================================================================
# LLM Usage (tracking de costos API)
# ============================================================================

PRECIOS_POR_MILLON: dict[str, tuple[float, float]] = {
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}


def _estimar_costo(modelo: str, input_tokens: int, output_tokens: int) -> float:
    precio_in, precio_out = PRECIOS_POR_MILLON.get(modelo, (0.40, 1.60))
    return (input_tokens / 1_000_000) * precio_in + (output_tokens / 1_000_000) * precio_out


async def log_llm_usage(
    telegram_id: Optional[int],
    servicio: str,
    modelo: str,
    input_tokens: int,
    output_tokens: int,
    rounds: int = 1,
) -> None:
    """Persiste registro de uso de API OpenAI para tracking de costos."""
    try:
        costo = _estimar_costo(modelo, input_tokens, output_tokens)
        async with async_session_factory() as session:
            uid = None
            if telegram_id is not None:
                uid = await _get_usuario_id(session, telegram_id)
            row = LlmUsage(
                usuario_id=uid,
                telegram_id=telegram_id,
                servicio=servicio,
                modelo=modelo,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                costo_estimado_usd=costo,
                rounds=rounds,
            )
            session.add(row)
            await session.commit()
    except Exception:
        logger.warning("Error guardando llm_usage servicio=%s", servicio, exc_info=True)


async def grabar_auditoria_turno(
    telegram_id: int,
    request_id: Optional[str] = None,
    prompt_usuario: Optional[str] = None,
    respuesta_bot: Optional[str] = None,
    tools_invocadas: Optional[list[dict]] = None,
    tokens_input: int = 0,
    tokens_output: int = 0,
    costo_estimado_usd: float = 0.0,
    duracion_ms: int = 0,
    error: Optional[str] = None,
) -> None:
    """Graba de forma segura un registro de auditoría de turno.

    Este método captura excepciones internamente y las loguea, de modo que
    un fallo en la auditoría nunca interrumpa el flujo del bot.
    """
    try:
        async with async_session_factory() as session:
            uid = await _get_usuario_id(session, telegram_id)
            row = AuditoriaTurno(
                telegram_id=telegram_id,
                usuario_id=uid,
                request_id=request_id,
                prompt_usuario=prompt_usuario,
                respuesta_bot=respuesta_bot,
                tools_invocadas=tools_invocadas,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                costo_estimado_usd=costo_estimado_usd,
                duracion_ms=duracion_ms,
                error=error,
            )
            session.add(row)
            await session.commit()
            logger.info("Grabada auditoría de turno para telegram_id=%s request_id=%s", telegram_id, request_id)
    except Exception:
        logger.exception(
            "Error persistiendo auditoria de turno para telegram_id=%s request_id=%s",
            telegram_id,
            request_id,
        )

