"""Capa de persistencia. Todo SQL vive aqui (no en tools, no en handlers)."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

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
    PersonalRecord,
    PlanDefinicion,
    PlanSuscripcion,
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


async def obtener_features_plan(plan: PlanSuscripcion) -> dict:
    """Lee features dinamicas desde plan_definicion. Cache 5 min in-process."""
    import time as _t

    key = plan.value
    ahora = _t.time()
    cached = _FEATURE_CACHE.get(key)
    if cached and (ahora - cached[0]) < 300:
        return cached[1]
    async with async_session_factory() as session:
        result = await session.execute(
            select(PlanDefinicion).where(PlanDefinicion.plan == plan)
        )
        definicion = result.scalar_one_or_none()
        features: dict = definicion.features if definicion else {}
    _FEATURE_CACHE[key] = (ahora, features)
    return features


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
            return False
        existente = await session.execute(
            select(UsuarioBloqueado).where(UsuarioBloqueado.usuario_id == uid)
        )
        if existente.scalar_one_or_none() is not None:
            return False
        bloqueo = UsuarioBloqueado(
            usuario_id=uid,
            motivo=motivo,
            bloqueado_por=admin_email,
        )
        session.add(bloqueo)
        await session.commit()
    _FEATURE_CACHE.clear()
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


async def listar_deportes_por_categoria(categoria: str) -> list[dict]:
    """Devuelve todos los deportes de una categoria."""
    if not _CATALOG_FULL_CACHE:
        await cargar_catalog_en_cache()
    return [d for d in _CATALOG_FULL_CACHE.values() if d["categoria"] == categoria]


async def slugs_disponibles() -> set[str]:
    """Devuelve set de todos los slugs activos. Util para validar guardar_perfil."""
    if not _CATALOG_CACHE:
        await cargar_catalog_en_cache()
    return set(_CATALOG_CACHE.keys())


async def actualizar_categoria_usuario(
    telegram_id: int, deporte_slug: str | None
) -> Optional[Usuario]:
    """Cuando se setea deporte_principal, actualiza categoria_deporte segun catalog."""
    if not deporte_slug:
        return None
    categoria = get_categoria_deporte(deporte_slug)
    try:
        cat_enum = CategoriaDeporte(categoria)
    except ValueError:
        cat_enum = CategoriaDeporte.INDOOR_FUERZA
    return await actualizar_usuario(
        telegram_id,
        deporte_principal=deporte_slug,
        categoria_deporte=cat_enum,
    )


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
    """Sesion skill urbano (skate/BMX/rollers/parkour/escalada)."""
    from src.db.models import TipoEjercicio

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
            subtipo=SubtipoSesion.SKILL,
            duracion_min=duracion_min,
            spot=spot or None,
            deporte_slug=deporte,
            foco_sesion=foco_sesion or None,
            trucos_intentados=trucos_intentados,
            trucos_aterrizados=trucos_aterrizados,
            num_caidas=num_caidas,
            sensacion_1_5=max(1, min(5, sensacion_1_5)),
            co_riders=co_riders or None,
            notas=notas or None,
        )
        session.add(sesion)
        await session.commit()
        await session.refresh(sesion)
        return sesion


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
