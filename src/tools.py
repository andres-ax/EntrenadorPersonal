"""Tools del agente OpenAI. Toda funcion con @function_tool debe:
- Ser async def.
- Docstring Google-style con seccion Args:.
- Devolver str JSON-serializable.
- No lanzar excepciones (try/except interno, devolver {"ok": False, "error": ...}).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta

from agents import function_tool

from src.db.repository import (
    actualizar_usuario,
    aceptar_modo_militar,
    cambiar_tono as repo_cambiar_tono,
    crear_compromiso,
    guardar_comida as repo_guardar_comida,
    guardar_metrica_corporal,
    guardar_pr as repo_guardar_pr,
    guardar_sesion as repo_guardar_sesion,
    guardar_sueno as repo_guardar_sueno,
    historial_peso as repo_historial_peso,
    incrementar_citado_compromiso,
    incrementar_streak,
    listar_prs,
    obtener_compromiso_activo,
    obtener_o_crear_usuario,
    obtener_o_crear_streak,
    obtener_pr_ejercicio,
    pausar_recordatorios,
    reporte_semanal,
    resumen_nutricional_dia,
    set_quiet_hours,
    usar_freeze_streak,
)
from src.db.repository import log_evento

logger = logging.getLogger(__name__)

TIPOS_ENTRENO_VALIDOS = {"fuerza", "cardio", "movilidad", "deporte"}
TIPOS_COMIDA_VALIDOS = {"desayuno", "almuerzo", "cena", "snack", "post_entreno"}
TONOS_VALIDOS = {"amigable", "firme", "militar"}
TIPOS_COMPROMISO_VALIDOS = {"entreno", "comida", "peso", "general"}
DEPORTES_VALIDOS = {
    "gimnasio",
    "crossfit",
    "running",
    "futbol",
    "calistenia",
    "natacion",
    "ciclismo",
    "yoga",
    "boxeo",
    "tenis",
}


def _safe_json_loads(raw: str, fallback=None):
    if not raw or raw.strip() == "":
        return fallback if fallback is not None else []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return fallback if fallback is not None else []


def _validar_fecha(fecha: str) -> str:
    try:
        date.fromisoformat(fecha)
        return fecha
    except (ValueError, TypeError):
        return date.today().isoformat()


def _error(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg})


def _ok(data: dict | None = None) -> str:
    out = {"ok": True}
    if data:
        out.update(data)
    return json.dumps(out, default=str)


# ============================================================================
# Perfil
# ============================================================================


@function_tool
async def obtener_perfil(telegram_id: int) -> str:
    """Obtiene el perfil completo del usuario.

    Args:
        telegram_id: ID de Telegram del usuario
    """
    try:
        u = await obtener_o_crear_usuario(telegram_id)
        return json.dumps(
            {
                "nombre": u.nombre or "",
                "edad": u.edad,
                "peso_kg": u.peso_kg,
                "altura_cm": u.altura_cm,
                "objetivo": u.objetivo or "",
                "nivel": u.nivel or "",
                "dias_entreno": u.dias_entreno,
                "deporte_principal": u.deporte_principal or "",
                "onboarding_completo": u.onboarding_completo or False,
                "tono": u.tono.value if u.tono else "firme",
                "timezone": u.timezone,
                "pais": u.pais,
                "modo_militar_aceptado": u.modo_militar_aceptado_en is not None,
            }
        )
    except Exception:
        logger.exception("Error en obtener_perfil")
        return _error("no pude consultar el perfil")


@function_tool
async def guardar_perfil(
    telegram_id: int,
    nombre: str = "",
    edad: int = 0,
    peso_kg: float = 0,
    altura_cm: float = 0,
    objetivo: str = "",
    nivel: str = "",
    dias_entreno: int = 0,
    deporte_principal: str = "",
    timezone: str = "",
    pais: str = "",
    onboarding_completo: bool = False,
) -> str:
    """Actualiza el perfil del usuario. Solo envia los campos con datos concretos.

    Args:
        telegram_id: ID de Telegram del usuario
        nombre: nombre del usuario
        edad: edad en anos
        peso_kg: peso en kilogramos
        altura_cm: altura en centimetros
        objetivo: ganar musculo, perder grasa, mantenerse, mejorar rendimiento
        nivel: principiante, intermedio, avanzado
        dias_entreno: dias por semana que entrena (1-7)
        deporte_principal: gimnasio, crossfit, running, futbol, calistenia, natacion, ciclismo, yoga, boxeo, tenis
        timezone: zona horaria IANA (ej: America/Bogota, America/Mexico_City, Europe/Madrid)
        pais: codigo ISO de 2 letras (CO, MX, AR, ES)
        onboarding_completo: True cuando tengas peso, altura, objetivo, nivel y dias_entreno
    """
    try:
        kwargs: dict = {}
        if nombre:
            kwargs["nombre"] = nombre
        if edad > 0:
            kwargs["edad"] = edad
        if peso_kg > 0:
            kwargs["peso_kg"] = peso_kg
        if altura_cm > 0:
            kwargs["altura_cm"] = altura_cm
        if objetivo:
            kwargs["objetivo"] = objetivo
        if nivel:
            kwargs["nivel"] = nivel
        if dias_entreno > 0:
            kwargs["dias_entreno"] = dias_entreno
        if deporte_principal:
            kwargs["deporte_principal"] = deporte_principal
        if timezone:
            kwargs["timezone"] = timezone
        if pais:
            kwargs["pais"] = pais.upper()[:8]
        if onboarding_completo:
            kwargs["onboarding_completo"] = True

        if not kwargs:
            return _error("No se proporcionaron campos para actualizar")

        await actualizar_usuario(telegram_id, **kwargs)
        return _ok({"campos_actualizados": list(kwargs.keys())})
    except Exception:
        logger.exception("Error en guardar_perfil")
        return _error("no pude guardar el perfil")


# ============================================================================
# Entrenamientos
# ============================================================================


@function_tool
async def registrar_entreno(
    telegram_id: int,
    fecha: str,
    tipo: str,
    duracion_min: int = 60,
    ejercicios_json: str = "[]",
    rpe: float = 0,
    notas: str = "",
) -> str:
    """Registra un entrenamiento completo. Tras registrarlo, incrementa el streak.

    Args:
        telegram_id: ID de Telegram del usuario
        fecha: formato YYYY-MM-DD
        tipo: DEBE ser uno de: fuerza, cardio, movilidad, deporte
        duracion_min: duracion en minutos
        ejercicios_json: JSON array de ejercicios, ej: [{"nombre":"sentadilla","series":4,"reps":8,"peso_kg":80}]
        rpe: esfuerzo percibido 1-10 (0 si no se sabe)
        notas: notas adicionales
    """
    try:
        fecha = _validar_fecha(fecha)
        tipo = tipo.lower().strip()
        if tipo not in TIPOS_ENTRENO_VALIDOS:
            return _error(f"tipo invalido: {tipo}. Validos: {sorted(TIPOS_ENTRENO_VALIDOS)}")

        ejercicios = _safe_json_loads(ejercicios_json, [])
        sesion = await repo_guardar_sesion(
            telegram_id,
            fecha,
            tipo,
            ejercicios,
            duracion_min,
            rpe if rpe > 0 else None,
            notas,
        )
        streak = await incrementar_streak(telegram_id, "entreno")
        await log_evento(telegram_id, "registro_entreno", {"tipo": tipo})
        return _ok(
            {
                "sesion_id": sesion.id,
                "ejercicios_registrados": len(ejercicios),
                "streak_dias": streak.dias_actuales,
            }
        )
    except Exception:
        logger.exception("Error en registrar_entreno")
        return _error("no pude registrar el entreno")


@function_tool
async def obtener_pr(telegram_id: int, ejercicio: str) -> str:
    """Consulta el Personal Record de un ejercicio especifico.

    Args:
        telegram_id: ID de Telegram del usuario
        ejercicio: nombre del ejercicio (ej: sentadilla, press banca, peso muerto)
    """
    try:
        pr = await obtener_pr_ejercicio(telegram_id, ejercicio)
        if pr:
            return json.dumps(
                {
                    "ejercicio": pr.ejercicio,
                    "peso_kg": pr.peso_kg,
                    "reps": pr.reps,
                    "fecha": str(pr.fecha),
                }
            )
        return json.dumps({"mensaje": f"No hay PR registrado para '{ejercicio}'"})
    except Exception:
        logger.exception("Error en obtener_pr")
        return _error("no pude consultar el PR")


@function_tool
async def guardar_pr(
    telegram_id: int,
    ejercicio: str,
    peso_kg: float,
    reps: int = 1,
    fecha: str = "",
) -> str:
    """Registra un nuevo Personal Record.

    Args:
        telegram_id: ID de Telegram del usuario
        ejercicio: nombre del ejercicio (ej: sentadilla, press banca, peso muerto)
        peso_kg: peso levantado en kg
        reps: repeticiones realizadas con ese peso
        fecha: formato YYYY-MM-DD (si vacio usa hoy)
    """
    try:
        fecha_obj = date.fromisoformat(_validar_fecha(fecha)) if fecha else date.today()
        pr = await repo_guardar_pr(telegram_id, ejercicio, peso_kg, reps, fecha_obj)
        await log_evento(telegram_id, "nuevo_pr", {"ejercicio": ejercicio, "peso": peso_kg})
        return _ok({"ejercicio": pr.ejercicio, "peso_kg": pr.peso_kg, "reps": pr.reps})
    except Exception:
        logger.exception("Error en guardar_pr")
        return _error("no pude guardar el PR")


@function_tool
async def listar_todos_prs(telegram_id: int) -> str:
    """Lista todos los Personal Records del usuario.

    Args:
        telegram_id: ID de Telegram del usuario
    """
    try:
        prs = await listar_prs(telegram_id)
        if not prs:
            return json.dumps({"mensaje": "Aun no tienes PRs registrados"})
        return json.dumps(
            [{"ejercicio": p.ejercicio, "peso_kg": p.peso_kg, "reps": p.reps} for p in prs]
        )
    except Exception:
        logger.exception("Error en listar_todos_prs")
        return _error("no pude listar los PRs")


# ============================================================================
# Comidas
# ============================================================================


@function_tool
async def registrar_comida(
    telegram_id: int,
    fecha: str,
    tipo: str,
    alimentos_json: str = "[]",
    calorias: int = 0,
    proteinas: float = 0,
    carbs: float = 0,
    grasas: float = 0,
) -> str:
    """Registra una comida del usuario.

    Args:
        telegram_id: ID de Telegram del usuario
        fecha: formato YYYY-MM-DD
        tipo: DEBE ser uno de: desayuno, almuerzo, cena, snack, post_entreno
        alimentos_json: JSON array de strings con alimentos, ej: ["avena","platano","leche"]
        calorias: calorias estimadas totales
        proteinas: gramos de proteina
        carbs: gramos de carbohidratos
        grasas: gramos de grasa
    """
    try:
        fecha = _validar_fecha(fecha)
        tipo = tipo.lower().strip()
        if tipo not in TIPOS_COMIDA_VALIDOS:
            return _error(f"tipo invalido: {tipo}. Validos: {sorted(TIPOS_COMIDA_VALIDOS)}")
        alimentos = _safe_json_loads(alimentos_json, [])
        await repo_guardar_comida(
            telegram_id, fecha, tipo, alimentos, calorias, proteinas, carbs, grasas
        )
        await log_evento(telegram_id, "registro_comida", {"tipo": tipo})
        return _ok({"tipo": tipo, "alimentos": alimentos})
    except Exception:
        logger.exception("Error en registrar_comida")
        return _error("no pude registrar la comida")


@function_tool
async def resumen_nutricional(telegram_id: int, fecha: str = "") -> str:
    """Resumen de calorias y macros de un dia.

    Args:
        telegram_id: ID de Telegram del usuario
        fecha: formato YYYY-MM-DD (si vacio usa hoy)
    """
    try:
        fecha_obj = date.fromisoformat(_validar_fecha(fecha)) if fecha else date.today()
        return json.dumps(await resumen_nutricional_dia(telegram_id, fecha_obj))
    except Exception:
        logger.exception("Error en resumen_nutricional")
        return _error("no pude calcular el resumen")


# ============================================================================
# Sueno y reporte
# ============================================================================


@function_tool
async def registrar_sueno(
    telegram_id: int,
    fecha: str,
    horas: float,
    calidad: int,
    notas: str = "",
) -> str:
    """Registra horas y calidad de sueno.

    Args:
        telegram_id: ID de Telegram del usuario
        fecha: formato YYYY-MM-DD (la fecha en que se desperto)
        horas: horas de sueno (ej: 7.5)
        calidad: 1=pesimo, 2=malo, 3=normal, 4=bueno, 5=excelente
        notas: notas opcionales
    """
    try:
        fecha = _validar_fecha(fecha)
        calidad = max(1, min(5, calidad))
        await repo_guardar_sueno(telegram_id, fecha, horas, calidad, notas)
        await log_evento(telegram_id, "registro_sueno", {"horas": horas, "calidad": calidad})
        return _ok({"horas": horas, "calidad": calidad})
    except Exception:
        logger.exception("Error en registrar_sueno")
        return _error("no pude registrar el sueno")


@function_tool
async def reporte_progreso(telegram_id: int) -> str:
    """Reporte semanal completo: sesiones, volumen, PRs y sueno de los ultimos 7 dias.

    Args:
        telegram_id: ID de Telegram del usuario
    """
    try:
        return json.dumps(await reporte_semanal(telegram_id), default=str)
    except Exception:
        logger.exception("Error en reporte_progreso")
        return _error("no pude generar el reporte")


# ============================================================================
# Peso e historial
# ============================================================================


@function_tool
async def registrar_peso(
    telegram_id: int,
    peso_kg: float,
    grasa_pct: float = 0,
    cintura_cm: float = 0,
) -> str:
    """Registra peso corporal actual.

    Args:
        telegram_id: ID de Telegram del usuario
        peso_kg: peso actual en kilogramos
        grasa_pct: porcentaje de grasa corporal (0 si no se sabe)
        cintura_cm: medida de cintura en cm (0 si no se sabe)
    """
    try:
        metrica = await guardar_metrica_corporal(
            telegram_id,
            peso_kg,
            grasa_pct if grasa_pct > 0 else None,
            cintura_cm if cintura_cm > 0 else None,
        )
        await log_evento(telegram_id, "registro_peso", {"peso_kg": peso_kg})
        return _ok(
            {
                "peso_kg": metrica.peso_kg,
                "fecha": str(metrica.fecha),
                "grasa_pct": metrica.grasa_pct,
                "cintura_cm": metrica.cintura_cm,
            }
        )
    except Exception:
        logger.exception("Error en registrar_peso")
        return _error("no pude registrar el peso")


@function_tool
async def consultar_historial_peso(telegram_id: int, limit: int = 10) -> str:
    """Devuelve los ultimos registros de peso.

    Args:
        telegram_id: ID de Telegram del usuario
        limit: cantidad maxima de registros (default 10)
    """
    try:
        registros = await repo_historial_peso(telegram_id, limit)
        if not registros:
            return json.dumps({"mensaje": "Aun no hay registros de peso"})
        return json.dumps(
            [
                {
                    "fecha": str(r.fecha),
                    "peso_kg": r.peso_kg,
                    "grasa_pct": r.grasa_pct,
                    "cintura_cm": r.cintura_cm,
                }
                for r in registros
            ]
        )
    except Exception:
        logger.exception("Error en consultar_historial_peso")
        return _error("no pude consultar el historial")


# ============================================================================
# Compromiso (CORE del coach molesto)
# ============================================================================


@function_tool
async def firmar_compromiso(
    telegram_id: int,
    objetivo_texto: str,
    deadline: str,
    frecuencia_semanal: int = 3,
    tipo_compromiso: str = "general",
    stake_simbolico: str = "",
) -> str:
    """Firma un compromiso del usuario con su objetivo. El bot lo citara cuando falle.

    Args:
        telegram_id: ID de Telegram del usuario
        objetivo_texto: objetivo concreto en primera persona (ej: 'Bajar 5kg en 8 semanas')
        deadline: fecha limite YYYY-MM-DD
        frecuencia_semanal: dias por semana que se compromete (1-7)
        tipo_compromiso: entreno, comida, peso o general
        stake_simbolico: que pierde si falla (ej: 'donar 50k a una causa que no me gusta')
    """
    try:
        tipo_compromiso = tipo_compromiso.lower().strip()
        if tipo_compromiso not in TIPOS_COMPROMISO_VALIDOS:
            return _error(f"tipo invalido. Validos: {sorted(TIPOS_COMPROMISO_VALIDOS)}")
        try:
            deadline_obj = date.fromisoformat(deadline)
        except ValueError:
            deadline_obj = date.today() + timedelta(days=60)
        if deadline_obj <= date.today():
            return _error("deadline debe ser futura")
        frecuencia_semanal = max(1, min(7, frecuencia_semanal))

        c = await crear_compromiso(
            telegram_id,
            objetivo_texto.strip(),
            deadline_obj,
            frecuencia_semanal,
            tipo_compromiso,
            stake_simbolico,
        )
        await log_evento(telegram_id, "firmar_compromiso", {"id": c.id})
        return _ok(
            {
                "id": c.id,
                "objetivo": c.objetivo_texto,
                "deadline": str(c.deadline),
                "frecuencia_semanal": c.frecuencia_semanal,
                "tipo": c.tipo_compromiso.value,
            }
        )
    except Exception:
        logger.exception("Error en firmar_compromiso")
        return _error("no pude firmar el compromiso")


@function_tool
async def consultar_compromiso(telegram_id: int) -> str:
    """Devuelve el compromiso activo (si existe) e incrementa citado_veces.

    Args:
        telegram_id: ID de Telegram del usuario
    """
    try:
        c = await obtener_compromiso_activo(telegram_id)
        if c is None:
            return json.dumps({"existe": False})
        await incrementar_citado_compromiso(c.id)
        return json.dumps(
            {
                "existe": True,
                "id": c.id,
                "objetivo": c.objetivo_texto,
                "deadline": str(c.deadline),
                "frecuencia_semanal": c.frecuencia_semanal,
                "tipo": c.tipo_compromiso.value,
                "stake": c.stake_simbolico,
                "dias_restantes": (c.deadline - date.today()).days,
                "citado_veces": c.citado_veces,
            }
        )
    except Exception:
        logger.exception("Error en consultar_compromiso")
        return _error("no pude consultar el compromiso")


# ============================================================================
# Tono y configuracion
# ============================================================================


@function_tool
async def cambiar_tono(telegram_id: int, tono: str) -> str:
    """Cambia el tono del coach. Para militar el usuario debe haber aceptado el disclaimer.

    Args:
        telegram_id: ID de Telegram del usuario
        tono: amigable, firme o militar
    """
    try:
        tono = tono.lower().strip()
        if tono not in TONOS_VALIDOS:
            return _error(f"tono invalido. Validos: {sorted(TONOS_VALIDOS)}")
        if tono == "militar":
            user = await obtener_o_crear_usuario(telegram_id)
            if user.modo_militar_aceptado_en is None:
                return _error(
                    "Para modo militar primero el usuario debe aceptar el disclaimer. "
                    "Usa confirmar_modo_militar antes."
                )
        await repo_cambiar_tono(telegram_id, tono)
        await log_evento(telegram_id, "cambio_tono", {"tono": tono})
        return _ok({"tono": tono})
    except Exception:
        logger.exception("Error en cambiar_tono")
        return _error("no pude cambiar el tono")


@function_tool
async def confirmar_modo_militar(telegram_id: int) -> str:
    """Marca al usuario como que acepto el disclaimer de modo militar.

    SOLO usar despues de que el usuario lea el disclaimer y diga 'acepto', 'si',
    'confirmo' o similar. No usar a la ligera.

    Args:
        telegram_id: ID de Telegram del usuario
    """
    try:
        await aceptar_modo_militar(telegram_id)
        await log_evento(telegram_id, "acepto_militar", {})
        return _ok({"aceptado": True})
    except Exception:
        logger.exception("Error en confirmar_modo_militar")
        return _error("no pude registrar la aceptacion")


@function_tool
async def configurar_quiet_hours(
    telegram_id: int, hora_inicio: str, hora_fin: str
) -> str:
    """Configura las horas de silencio del usuario (no te molesta entre esas horas).

    Args:
        telegram_id: ID de Telegram del usuario
        hora_inicio: HH:MM 24h (ej: 22:00)
        hora_fin: HH:MM 24h (ej: 07:00)
    """
    try:
        await set_quiet_hours(telegram_id, hora_inicio, hora_fin)
        await log_evento(
            telegram_id, "quiet_hours", {"inicio": hora_inicio, "fin": hora_fin}
        )
        return _ok({"inicio": hora_inicio, "fin": hora_fin})
    except Exception:
        logger.exception("Error en configurar_quiet_hours")
        return _error("no pude configurar las horas")


@function_tool
async def pausar(telegram_id: int, dias: int = 1) -> str:
    """Pausa los recordatorios por N dias. El bot no envia nada hasta que pase.

    Args:
        telegram_id: ID de Telegram del usuario
        dias: cantidad de dias (1-30)
    """
    try:
        dias = max(1, min(30, dias))
        await pausar_recordatorios(telegram_id, dias)
        await log_evento(telegram_id, "pausa", {"dias": dias})
        return _ok({"dias": dias})
    except Exception:
        logger.exception("Error en pausar")
        return _error("no pude aplicar la pausa")


@function_tool
async def usar_dia_libre(telegram_id: int) -> str:
    """Usa 1 freeze para no romper el streak hoy. Devuelve si tenia disponibles.

    Args:
        telegram_id: ID de Telegram del usuario
    """
    try:
        ok = await usar_freeze_streak(telegram_id, "entreno")
        await log_evento(telegram_id, "dia_libre", {"ok": ok})
        if not ok:
            return _error("no tienes freezes disponibles. Se regenera 1 cada 30 dias.")
        return _ok({"freeze_consumido": True})
    except Exception:
        logger.exception("Error en usar_dia_libre")
        return _error("no pude usar el freeze")


@function_tool
async def consultar_streak(telegram_id: int, tipo: str = "entreno") -> str:
    """Consulta el streak actual del usuario.

    Args:
        telegram_id: ID de Telegram del usuario
        tipo: entreno, comida, sueno, peso o todos
    """
    try:
        s = await obtener_o_crear_streak(telegram_id, tipo)
        return json.dumps(
            {
                "tipo": s.tipo_streak.value,
                "dias_actuales": s.dias_actuales,
                "max_historico": s.max_historico,
                "ultima_fecha": str(s.ultima_fecha) if s.ultima_fecha else None,
                "freezes_disponibles": s.freezes_disponibles,
            }
        )
    except Exception:
        logger.exception("Error en consultar_streak")
        return _error("no pude consultar el streak")
