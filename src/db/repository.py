import json
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.db.connection import async_session_factory
from src.db.models import (
    Comida,
    EjercicioRealizado,
    MetricaCorporal,
    MetricaSueno,
    PersonalRecord,
    SesionEntrenamiento,
    TipoComida,
    TipoEjercicio,
    Usuario,
)


async def _get_usuario_id(session, telegram_id: int) -> Optional[int]:
    """Resuelve usuario_id dentro de una sesion existente sin abrir otra."""
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


async def eliminar_usuario(telegram_id: int) -> bool:
    """Elimina el usuario y todos sus datos (cascade). Retorna True si existia."""
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
    telegram_id: int, ejercicio: str, peso_kg: float, reps: int, fecha: Optional[date] = None
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


async def resumen_nutricional_dia(telegram_id: int, fecha: Optional[date] = None) -> dict:
    async with async_session_factory() as session:
        uid = await _get_usuario_id(session, telegram_id)
        if uid is None:
            return {"total_calorias": 0, "total_proteinas": 0, "total_carbs": 0, "total_grasas": 0, "comidas": []}

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
    """Resumen de sueno usando una sesion existente."""
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
                "dias_entrenados": 0, "volumen_total_kg": 0, "total_ejercicios": 0,
                "nuevos_prs": [], "sueno": {}, "periodo": "",
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

        volumen = 0
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
