"""Tools del agente OpenAI. Toda funcion con @function_tool debe:
- Ser async def.
- Docstring Google-style con seccion Args:.
- Devolver str JSON-serializable.
- No lanzar excepciones (try/except interno, devolver {"ok": False, "error": ...}).
"""
from __future__ import annotations

import functools
import json
import logging
import random
import time
from datetime import date, datetime, time as dtime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from agents import function_tool

from src.db.repository import (
    actualizar_usuario,
    aceptar_modo_militar,
    cambiar_tono as repo_cambiar_tono,
    crear_compromiso,
    crear_recordatorio as repo_crear_recordatorio,
    desactivar_recordatorio as repo_desactivar_recordatorio,
    guardar_comida as repo_guardar_comida,
    guardar_metrica_corporal,
    guardar_pr as repo_guardar_pr,
    guardar_pr_tiempo as repo_guardar_pr_tiempo,
    guardar_pr_truco as repo_guardar_pr_truco,
    guardar_pr_via_escalada as repo_guardar_pr_via,
    guardar_sesion as repo_guardar_sesion,
    guardar_sesion_skill as repo_guardar_sesion_skill,
    guardar_sesion_sparring as repo_guardar_sesion_sparring,
    guardar_sueno as repo_guardar_sueno,
    historial_peso as repo_historial_peso,
    incrementar_citado_compromiso,
    incrementar_streak,
    listar_prs,
    listar_recordatorios as repo_listar_recordatorios,
    listar_sesiones_skill as repo_listar_sesiones_skill,
    listar_sparring_reciente as repo_listar_sparring_reciente,
    listar_trucos_aterrizados as repo_listar_trucos,
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
from src.telegram.bot_setup import obtener_application
from src.telegram.scheduler import (
    cancelar_recordatorio_jobs,
    programar_recordatorio_en_jobqueue,
)

logger = logging.getLogger(__name__)


_SENSITIVE_ARG_NAMES = {"password", "token", "secret", "comprobante_url"}


def _summary_arg(value: Any) -> Any:
    """Resume valores grandes para evitar logs gigantes (e.g. URLs base64)."""
    if isinstance(value, str) and len(value) > 80:
        return f"{value[:60]}...({len(value)}c)"
    if isinstance(value, (list, tuple, set)) and len(value) > 8:
        return f"<{type(value).__name__} len={len(value)}>"
    if isinstance(value, dict) and len(value) > 8:
        return f"<dict keys={list(value)[:8]}...>"
    return value


def _looks_ok(result: Any) -> bool:
    """Heuristica: detecta ok=true en el JSON-string que retornan las tools."""
    if not isinstance(result, str):
        return True
    head = result.lstrip()[:60].lower()
    if '"ok":false' in head or '"ok": false' in head:
        return False
    if '"error"' in head:
        return False
    return True


def _log_tool(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorador interno que envuelve cada @function_tool con logs.

    Loguea entrada (con args sanitizados), latencia y exito/error. Mantiene la
    signature original via functools.wraps para que `function_tool` siga
    pudiendo inspeccionarla y generar el schema JSON correcto.

    En caso de excepcion (no esperada porque las tools deben retornar JSON
    con ok=False) se logea con stacktrace y se reentrega para que la
    pipeline del agente la maneje.
    """
    tool_name = fn.__name__

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        safe_args = [
            _summary_arg(a) for a in args
        ]
        safe_kwargs = {
            k: ("***" if k in _SENSITIVE_ARG_NAMES else _summary_arg(v))
            for k, v in kwargs.items()
        }
        logger.info(
            "tool.%s call args=%s kwargs=%s",
            tool_name,
            safe_args,
            safe_kwargs,
        )
        t0 = time.perf_counter()
        try:
            result = await fn(*args, **kwargs)
        except Exception:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.exception(
                "tool.%s raised elapsed=%.1fms", tool_name, elapsed_ms
            )
            raise
        elapsed_ms = (time.perf_counter() - t0) * 1000
        ok = _looks_ok(result)
        log_fn = logger.info if ok else logger.warning
        log_fn(
            "tool.%s done ok=%s elapsed=%.1fms",
            tool_name,
            ok,
            elapsed_ms,
        )
        return result

    return wrapper


TIPOS_ENTRENO_VALIDOS = {"fuerza", "cardio", "movilidad", "deporte"}
TIPOS_COMIDA_VALIDOS = {"desayuno", "almuerzo", "cena", "snack", "post_entreno"}
TONOS_VALIDOS = {"amigable", "firme", "militar"}
TIPOS_COMPROMISO_VALIDOS = {"entreno", "comida", "peso", "general"}
DEPORTES_VALIDOS = {
    # urbano
    "bmx", "skate", "rollers", "patinaje_velocidad", "patinaje_artistico",
    "scooter", "parkour", "surf", "kitesurf", "sup", "slacklining",
    # escalada
    "climbing",
    # combate
    "boxeo", "muay_thai", "bjj", "mma", "karate", "taekwondo", "judo",
    "kickboxing", "wrestling", "capoeira", "krav_maga", "esgrima",
    # equipo
    "futbol", "baloncesto", "voley", "voley_playa", "beisbol", "softbol",
    "rugby", "hockey", "ultimate", "padel", "tenis",
    # outdoor endurance
    "running", "trail", "triatlon", "duatlon", "ocr", "mtb", "ciclismo",
    "atletismo",
    # indoor fuerza
    "gimnasio", "crossfit", "calistenia", "powerlifting", "halterofilia",
    "funcional", "pilates", "yoga", "pole", "aerial",
    # acuatico
    "natacion", "waterpolo", "apnea", "buceo",
    # ecuestre
    "equitacion", "polo", "caballo_paso",
    # motor
    "karting", "motocross", "enduro_moto",
    # tradicional CO
    "tejo", "coleo",
    # alias comunes (preservar back-compat)
    "rolling", "patinaje", "escalada", "soccer", "basket", "volley",
}


def _safe_json_loads(raw: str, fallback=None):
    if not raw or raw.strip() == "":
        return fallback if fallback is not None else []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return fallback if fallback is not None else []


_TZ_FALLBACK = "America/Bogota"


async def _tz_usuario(telegram_id: int) -> ZoneInfo:
    """Devuelve el ZoneInfo configurado en el perfil del usuario.

    Cae a `America/Bogota` si el usuario no existe, no tiene tz o la tz es
    invalida. Evita usar `date.today()` (que toma UTC del servidor Railway)
    cuando se necesita la fecha local del usuario.
    """
    try:
        u = await obtener_o_crear_usuario(telegram_id)
        tz_name = u.timezone or _TZ_FALLBACK
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo(_TZ_FALLBACK)


async def _hoy_usuario(telegram_id: int) -> date:
    """Fecha de hoy en la zona horaria del usuario."""
    tz = await _tz_usuario(telegram_id)
    return datetime.now(tz).date()


async def _ahora_usuario(telegram_id: int) -> datetime:
    """Datetime aware (con tz) de ahora en la zona horaria del usuario."""
    tz = await _tz_usuario(telegram_id)
    return datetime.now(tz)


def _validar_fecha(fecha: str) -> str:
    """Valida formato YYYY-MM-DD. Devuelve "" si invalido (caller decide default).

    NO usa `date.today()` para el fallback porque eso tomaria UTC del servidor;
    los callers deben usar `_hoy_usuario(telegram_id)` para obtener hoy en la
    zona del usuario.
    """
    try:
        date.fromisoformat(fecha)
        return fecha
    except (ValueError, TypeError):
        return ""


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
@_log_tool
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
@_log_tool
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
        deporte_principal: slug del deporte (acepta 67 deportes: bmx, skate, rollers, climbing, boxeo, bjj, mma, futbol, padel, trail, mtb, ciclismo, gimnasio, crossfit, natacion, apnea, equitacion, karting, tejo, etc). Lista completa en DeporteCatalogo.
        timezone: zona horaria IANA (ej: America/Bogota, America/Mexico_City, Europe/Madrid)
        pais: codigo ISO de 2 letras (CO, MX, AR, ES)
        onboarding_completo: True cuando tengas peso, altura, objetivo, nivel y dias_entreno
    """
    try:
        kwargs: dict = {}
        if nombre:
            # Normaliza capitalizacion: "ANdy" -> "Andy", "maria fernanda" -> "Maria Fernanda".
            # Si el usuario tipea mayusculas raras durante onboarding, el compromiso
            # firmado se ve raro. .title() es buena heuristica para nombres simples.
            kwargs["nombre"] = nombre.strip().title()
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
            slug = deporte_principal.lower().strip()
            kwargs["deporte_principal"] = slug
            # Auto-derivar categoria desde el catalog para el sub-prompt
            from src.db.models import CategoriaDeporte
            from src.db.repository import get_categoria_deporte

            try:
                kwargs["categoria_deporte"] = CategoriaDeporte(
                    get_categoria_deporte(slug)
                )
            except ValueError:
                kwargs["categoria_deporte"] = CategoriaDeporte.INDOOR_FUERZA
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
@_log_tool
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
@_log_tool
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
@_log_tool
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
        fecha: formato YYYY-MM-DD (si vacio usa hoy en la tz del usuario)
    """
    try:
        fecha_norm = _validar_fecha(fecha) if fecha else ""
        fecha_obj = (
            date.fromisoformat(fecha_norm)
            if fecha_norm
            else await _hoy_usuario(telegram_id)
        )
        pr = await repo_guardar_pr(telegram_id, ejercicio, peso_kg, reps, fecha_obj)
        await log_evento(telegram_id, "nuevo_pr", {"ejercicio": ejercicio, "peso": peso_kg})
        try:
            from src.cache import get_redis
            import json as _json

            client = await get_redis()
            await client.publish(
                "pr_publicar_canal",
                _json.dumps(
                    {
                        "telegram_id": telegram_id,
                        "pr_id": pr.id,
                        "ejercicio": pr.ejercicio,
                        "peso_kg": pr.peso_kg,
                        "reps": pr.reps,
                    }
                ),
            )
        except Exception:
            pass
        return _ok({"ejercicio": pr.ejercicio, "peso_kg": pr.peso_kg, "reps": pr.reps})
    except Exception:
        logger.exception("Error en guardar_pr")
        return _error("no pude guardar el PR")


@function_tool
@_log_tool
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
@_log_tool
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
@_log_tool
async def resumen_nutricional(telegram_id: int, fecha: str = "") -> str:
    """Resumen de calorias y macros de un dia.

    Args:
        telegram_id: ID de Telegram del usuario
        fecha: formato YYYY-MM-DD (si vacio usa hoy en la tz del usuario)
    """
    try:
        fecha_norm = _validar_fecha(fecha) if fecha else ""
        fecha_obj = (
            date.fromisoformat(fecha_norm)
            if fecha_norm
            else await _hoy_usuario(telegram_id)
        )
        return json.dumps(await resumen_nutricional_dia(telegram_id, fecha_obj))
    except Exception:
        logger.exception("Error en resumen_nutricional")
        return _error("no pude calcular el resumen")


# ============================================================================
# Sueno y reporte
# ============================================================================


@function_tool
@_log_tool
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
@_log_tool
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
@_log_tool
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
@_log_tool
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
@_log_tool
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
        hoy = await _hoy_usuario(telegram_id)
        try:
            deadline_obj = date.fromisoformat(deadline)
        except ValueError:
            deadline_obj = hoy + timedelta(days=60)
        if deadline_obj <= hoy:
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
@_log_tool
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
        hoy = await _hoy_usuario(telegram_id)
        return json.dumps(
            {
                "existe": True,
                "id": c.id,
                "objetivo": c.objetivo_texto,
                "deadline": str(c.deadline),
                "frecuencia_semanal": c.frecuencia_semanal,
                "tipo": c.tipo_compromiso.value,
                "stake": c.stake_simbolico,
                "dias_restantes": (c.deadline - hoy).days,
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
@_log_tool
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
@_log_tool
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
@_log_tool
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
@_log_tool
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
@_log_tool
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
@_log_tool
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


# ============================================================================
# Engagement (Fase 5/6/7)
# ============================================================================


@function_tool
@_log_tool
async def proponer_ejercicio_aleatorio(telegram_id: int) -> str:
    """Sortea un foco de ejercicio para hoy. Solo usar si el usuario dice 'no se que entrenar'.

    Args:
        telegram_id: ID de Telegram del usuario
    """
    opciones = ["push", "pull", "piernas", "core + cardio", "movilidad activa", "descanso activo"]
    eleccion = random.choice(opciones)
    await log_evento(telegram_id, "rueda_ejercicio", {"eleccion": eleccion})
    return _ok({"foco_propuesto": eleccion, "mensaje": f"Hoy toca: {eleccion}"})


@function_tool
@_log_tool
async def dar_premio_motivacional(telegram_id: int) -> str:
    """Otorga un sticker/mensaje motivacional aleatorio. Variable reward.

    Args:
        telegram_id: ID de Telegram del usuario
    """
    mensajes = [
        "Crack, recuerda por que arrancaste.",
        "Pequenos pasos suman. Hoy es uno mas.",
        "Tu yo de manana te agradece.",
        "La consistencia gana a la motivacion.",
        "Una serie mas. Solo una.",
        "Eres mas fuerte que tu peor dia.",
    ]
    await log_evento(telegram_id, "premio_motivacional", {})
    return _ok({"mensaje": random.choice(mensajes)})


def _detectar_logro_streak(dias: int) -> str | None:
    if dias in (7, 30, 100, 365):
        return f"streak_{dias}"
    return None


@function_tool
@_log_tool
async def verificar_logros(telegram_id: int) -> str:
    """Verifica si el usuario alcanzo un hito (streak 7/30/100/365). Devuelve string del logro o vacio.

    Llamar despues de registrar_entreno.

    Args:
        telegram_id: ID de Telegram del usuario
    """
    try:
        s = await obtener_o_crear_streak(telegram_id, "entreno")
        logro = _detectar_logro_streak(s.dias_actuales)
        if logro:
            await log_evento(telegram_id, "logro_alcanzado", {"logro": logro})
            return _ok(
                {"logro": logro, "dias": s.dias_actuales, "mensaje": f"Hito {logro}!"}
            )
        return _ok({"logro": None, "dias": s.dias_actuales})
    except Exception:
        logger.exception("Error en verificar_logros")
        return _error("no pude verificar")


@function_tool
@_log_tool
async def consultar_resumen_visual(telegram_id: int) -> str:
    """Devuelve info para que el handler genere un chart visual del progreso.

    Args:
        telegram_id: ID de Telegram del usuario
    """
    try:
        rep = await reporte_semanal(telegram_id)
        return json.dumps(
            {
                "tipo": "chart_resumen_semanal",
                "data": rep,
                "instruccion": "El bot enviara una imagen con el resumen visual.",
            },
            default=str,
        )
    except Exception:
        return _error("no pude generar")


# ============================================================================
# PR3 - Tools deportes urbanos (BMX, skate, rollers, parkour, escalada)
# ============================================================================


DEPORTES_URBANO_TRICKS = {
    "skate", "bmx", "rollers", "parkour", "scooter",
}


@function_tool
@_log_tool
async def registrar_truco_aterrizado(
    telegram_id: int,
    deporte: str,
    nombre_truco: str,
    spot: str = "",
    video_url: str = "",
    intentos: int = 1,
    es_primer_aterrizaje: bool = True,
    fecha: str = "",
) -> str:
    """Registra un truco aterrizado en deportes urbanos (skate/BMX/rollers/parkour).

    Si es_primer_aterrizaje=True crea PersonalRecord(tipo_pr=TRUCO).
    Si es repeticion (False), solo loggea evento.

    Args:
        telegram_id: ID de Telegram del usuario
        deporte: skate, bmx, rollers, parkour, scooter
        nombre_truco: nombre del truco (ej "kickflip", "tailwhip", "soul grind", "wallrun")
        spot: lugar (ej "Salitre BMX", "Aranjuez skatepark", "Suesca")
        video_url: URL del clip si filmo
        intentos: numero de intentos hasta lograrlo
        es_primer_aterrizaje: True si es la primera vez que aterriza este truco
        fecha: YYYY-MM-DD (si vacio usa hoy)
    """
    try:
        deporte = deporte.lower().strip()
        if deporte not in DEPORTES_URBANO_TRICKS:
            return _error(
                f"deporte invalido para truco: {deporte}. Validos: {sorted(DEPORTES_URBANO_TRICKS)}"
            )
        if not nombre_truco or len(nombre_truco) > 80:
            return _error("nombre_truco requerido (max 80 chars)")
        fecha_norm = _validar_fecha(fecha) if fecha else ""
        fecha_obj = (
            date.fromisoformat(fecha_norm)
            if fecha_norm
            else await _hoy_usuario(telegram_id)
        )
        if es_primer_aterrizaje:
            pr = await repo_guardar_pr_truco(
                telegram_id, deporte, nombre_truco,
                spot=spot, video_url=video_url, fecha=fecha_obj,
            )
            await log_evento(
                telegram_id, "truco_PR", {"deporte": deporte, "truco": nombre_truco}
            )
            return _ok({
                "pr_id": pr.id, "es_pr_nuevo": True,
                "deporte": deporte, "truco": nombre_truco,
            })
        await log_evento(
            telegram_id, "truco_repeticion",
            {"deporte": deporte, "truco": nombre_truco, "intentos": intentos},
        )
        return _ok({"es_pr_nuevo": False, "registrado": True})
    except Exception:
        logger.exception("Error en registrar_truco_aterrizado")
        return _error("no pude guardar el truco")


@function_tool
@_log_tool
async def registrar_sesion_skill(
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
    fecha: str = "",
) -> str:
    """Registra sesion completa de deporte urbano (skate/BMX/rollers/parkour/scooter).

    NO uses esta tool para gym (usa registrar_entreno). Esta es solo skill sports.
    Si num_caidas >= 3 o sensacion_1_5 <= 2, el coach debe sugerir descanso al dia
    siguiente y screening pasivo de concusion (REGLA #13).

    Args:
        telegram_id: ID Telegram
        deporte: skate, bmx, rollers, parkour, scooter
        duracion_min: minutos totales de sesion (5-480)
        spot: nombre del lugar
        foco_sesion: ej "kickflip", "transition", "free flow", "spot nuevo"
        trucos_intentados: cuantos trucos intento
        trucos_aterrizados: cuantos aterrizo
        num_caidas: numero de caidas notables (>2 = bandera)
        sensacion_1_5: 1=pesimo, 5=excelente
        co_riders: usernames de companeros separados por coma
        notas: texto libre
        fecha: YYYY-MM-DD
    """
    try:
        deporte = deporte.lower().strip()
        if deporte not in DEPORTES_URBANO_TRICKS:
            return _error(f"deporte invalido: {deporte}")
        if not (5 <= duracion_min <= 480):
            return _error("duracion fuera de rango (5-480 min)")
        if not (1 <= sensacion_1_5 <= 5):
            return _error("sensacion debe ser 1-5")
        fecha_norm = _validar_fecha(fecha) if fecha else ""
        fecha_obj = (
            date.fromisoformat(fecha_norm)
            if fecha_norm
            else await _hoy_usuario(telegram_id)
        )
        sesion = await repo_guardar_sesion_skill(
            telegram_id, deporte=deporte, duracion_min=duracion_min,
            spot=spot, foco_sesion=foco_sesion,
            trucos_intentados=trucos_intentados,
            trucos_aterrizados=trucos_aterrizados,
            num_caidas=num_caidas, sensacion_1_5=sensacion_1_5,
            co_riders=co_riders, notas=notas, fecha=fecha_obj,
        )
        await incrementar_streak(telegram_id, "entreno")
        await log_evento(
            telegram_id, "sesion_skill",
            {"deporte": deporte, "duracion": duracion_min, "caidas": num_caidas},
        )
        return _ok({
            "sesion_id": sesion.id, "deporte": deporte,
            "aterrizados": trucos_aterrizados, "intentados": trucos_intentados,
            "alerta_caidas": num_caidas >= 3,
            "alerta_sensacion": sensacion_1_5 <= 2,
        })
    except Exception:
        logger.exception("Error en registrar_sesion_skill")
        return _error("no pude registrar la sesion")


@function_tool
@_log_tool
async def registrar_via_escalada(
    telegram_id: int,
    nombre_via: str,
    grado: str,
    spot: str,
    estilo: str = "redpoint",
    intentos: int = 1,
    lesion_dedo_si_no: bool = False,
    fecha: str = "",
) -> str:
    """Registra una via o boulder escalada (climbing).

    NO recomendar hangboard a principiantes (<12-18 meses). Si lesion_dedo_si_no
    el coach debe sugerir off de crimping/hangboard (Schweizer 2012 poleas A2/A4).

    Args:
        telegram_id: ID Telegram
        nombre_via: nombre de la via o boulder
        grado: YDS (5.10a), Fontainebleau (V4), francesa (6c)
        spot: Suesca, San Gil/La Mojarra, Macheta, El Penol, Tatacoa, Toluviejo
        estilo: on_sight | flash | redpoint | repunto | proyecto | boulder
        intentos: numero de intentos hasta enviarla
        lesion_dedo_si_no: True si tuvo molestia/dolor en dedos
        fecha: YYYY-MM-DD
    """
    ESTILOS = {"on_sight", "flash", "redpoint", "repunto", "proyecto", "boulder"}
    try:
        estilo = estilo.lower().strip().replace("-", "_").replace(" ", "_")
        if estilo == "onsight":
            estilo = "on_sight"
        if estilo not in ESTILOS:
            return _error(f"estilo invalido: {estilo}. Validos: {sorted(ESTILOS)}")
        import re
        if not re.match(r"^(5\.\d{1,2}[a-d]?|V\d{1,2}|[3-9][a-c]\+?)$", grado):
            return _error(f"grado invalido: {grado}. Usa 5.10a, V4 o 6c+")
        fecha_norm = _validar_fecha(fecha) if fecha else ""
        fecha_obj = (
            date.fromisoformat(fecha_norm)
            if fecha_norm
            else await _hoy_usuario(telegram_id)
        )
        pr = await repo_guardar_pr_via(
            telegram_id, nombre_via, grado, spot, estilo=estilo, fecha=fecha_obj,
            notas=f"intentos={intentos}; lesion_dedo={lesion_dedo_si_no}",
        )
        await log_evento(
            telegram_id, "via_escalada",
            {"grado": grado, "estilo": estilo, "spot": spot, "lesion_dedo": lesion_dedo_si_no},
        )
        return _ok({
            "pr_id": pr.id, "via": nombre_via, "grado": grado, "estilo": estilo,
            "alerta_dedos": lesion_dedo_si_no,
        })
    except Exception:
        logger.exception("Error en registrar_via_escalada")
        return _error("no pude registrar la via")


@function_tool
@_log_tool
async def consultar_progreso_skill(
    telegram_id: int,
    deporte: str,
    ventana_dias: int = 30,
) -> str:
    """Resumen de progreso skill en deportes urbanos (no kg, sino sesiones + trucos).

    Args:
        telegram_id: ID Telegram
        deporte: skate, bmx, rollers, parkour, scooter
        ventana_dias: ventana de analisis (7-365, default 30)
    """
    try:
        deporte = deporte.lower().strip()
        if not (7 <= ventana_dias <= 365):
            return _error("ventana_dias fuera de rango (7-365)")
        sesiones = await repo_listar_sesiones_skill(telegram_id, deporte, ventana_dias)
        trucos_recientes = await repo_listar_trucos(telegram_id, deporte)
        horas_totales = sum(s.duracion_min or 0 for s in sesiones) / 60
        spots = list({s.spot for s in sesiones if s.spot})
        caidas_total = sum(s.num_caidas or 0 for s in sesiones)
        return _ok({
            "deporte": deporte, "ventana_dias": ventana_dias,
            "sesiones": len(sesiones), "horas_totales": round(horas_totales, 1),
            "spots_frecuentados": spots[:5],
            "trucos_PR_nuevos": [
                {"truco": t.ejercicio, "fecha": str(t.fecha)} for t in trucos_recientes[:10]
            ],
            "total_caidas": caidas_total,
        })
    except Exception:
        logger.exception("Error en consultar_progreso_skill")
        return _error("no pude generar reporte")


# ============================================================================
# PR3 - Tools deportes combate (BJJ, MMA, boxeo, muay thai, etc)
# ============================================================================


ESTILOS_COMBATE = {
    "boxeo", "bjj", "mma", "muay_thai", "kickboxing", "wrestling",
    "judo", "karate", "taekwondo", "capoeira", "krav_maga",
}


@function_tool
@_log_tool
async def registrar_sparring(
    telegram_id: int,
    estilo: str,
    rounds: int,
    duracion_round_min: int = 3,
    intensidad_1_10: int = 5,
    golpe_cabeza_fuerte: bool = False,
    notas: str = "",
    fecha: str = "",
) -> str:
    """Registra sesion de sparring (combate). Subtipo=SPARRING.

    Si golpe_cabeza_fuerte=True el coach DEBE activar screening de concusion
    (REGLA #13). Si rounds*duracion > 90min el coach debe alertar sobre carga
    excesiva.

    Args:
        telegram_id: ID Telegram
        estilo: boxeo, bjj, mma, muay_thai, kickboxing, wrestling, judo, karate, taekwondo, capoeira, krav_maga
        rounds: numero de rounds o rolls
        duracion_round_min: minutos por round (boxeo 3, BJJ rolls 5-7)
        intensidad_1_10: 1-3 light/flow, 4-6 medium, 7-10 hard
        golpe_cabeza_fuerte: True activa screening concusion (REGLA #13)
        notas: texto libre
        fecha: YYYY-MM-DD
    """
    try:
        estilo = estilo.lower().strip().replace(" ", "_")
        if estilo not in ESTILOS_COMBATE:
            return _error(f"estilo invalido: {estilo}. Validos: {sorted(ESTILOS_COMBATE)}")
        if not (1 <= intensidad_1_10 <= 10):
            return _error("intensidad debe ser 1-10")
        if rounds < 1 or rounds > 30:
            return _error("rounds fuera de rango (1-30)")
        fecha_norm = _validar_fecha(fecha) if fecha else ""
        fecha_obj = (
            date.fromisoformat(fecha_norm)
            if fecha_norm
            else await _hoy_usuario(telegram_id)
        )
        sesion = await repo_guardar_sesion_sparring(
            telegram_id, estilo=estilo, rounds=rounds,
            duracion_round_min=duracion_round_min,
            intensidad_1_10=intensidad_1_10,
            golpe_cabeza_fuerte=golpe_cabeza_fuerte,
            notas=notas, fecha=fecha_obj,
        )
        await incrementar_streak(telegram_id, "entreno")
        await log_evento(
            telegram_id, "sparring",
            {
                "estilo": estilo, "rounds": rounds, "intensidad": intensidad_1_10,
                "golpe_cabeza": golpe_cabeza_fuerte,
            },
        )
        carga_alta = rounds * duracion_round_min > 90
        return _ok({
            "sesion_id": sesion.id, "estilo": estilo, "rounds": rounds,
            "intensidad": intensidad_1_10,
            "alerta_carga_alta": carga_alta,
            "alerta_concusion": golpe_cabeza_fuerte,
        })
    except Exception:
        logger.exception("Error en registrar_sparring")
        return _error("no pude registrar el sparring")


@function_tool
@_log_tool
async def registrar_pelea(
    telegram_id: int,
    estilo: str,
    resultado: str,
    metodo: str,
    peso_pesaje_kg: float,
    peso_dia_pelea_kg: float = 0.0,
    opponent_record: str = "",
    round_final: int = 0,
    spot: str = "",
    fecha: str = "",
) -> str:
    """Registra pelea oficial (amateur o profesional).

    Calcula rebound peso pesaje vs dia pelea (Matthews 2019). Si rebound > 10%
    activa educacion sobre cut responsable.

    Args:
        telegram_id: ID Telegram
        estilo: boxeo, mma, muay_thai, bjj, kickboxing, wrestling
        resultado: ganada, perdida, draw, no_contest, dq
        metodo: ko, tko, decision_unanime, decision_dividida, decision_mayoritaria, sumision, dq, draw
        peso_pesaje_kg: peso oficial del pesaje
        peso_dia_pelea_kg: peso real dia de pelea (mide rebound)
        opponent_record: ej "12-3-1"
        round_final: round en que termino (0 si fue decision)
        spot: lugar / nombre del evento
        fecha: YYYY-MM-DD
    """
    RESULTADOS = {"ganada", "perdida", "draw", "no_contest", "dq"}
    METODOS = {
        "ko", "tko", "decision_unanime", "decision_dividida",
        "decision_mayoritaria", "sumision", "dq", "draw",
    }
    try:
        estilo = estilo.lower().strip().replace(" ", "_")
        if estilo not in ESTILOS_COMBATE:
            return _error(f"estilo invalido: {estilo}")
        resultado = resultado.lower().strip()
        metodo = metodo.lower().strip().replace(" ", "_")
        if resultado not in RESULTADOS:
            return _error(f"resultado invalido. Validos: {sorted(RESULTADOS)}")
        if metodo not in METODOS:
            return _error(f"metodo invalido. Validos: {sorted(METODOS)}")
        if not (40 <= peso_pesaje_kg <= 200):
            return _error("peso_pesaje fuera de rango")

        rebound_pct = None
        alerta_rebound = False
        if peso_dia_pelea_kg and peso_pesaje_kg:
            rebound_kg = peso_dia_pelea_kg - peso_pesaje_kg
            rebound_pct = round((rebound_kg / peso_pesaje_kg) * 100, 2)
            alerta_rebound = rebound_pct > 10

        await log_evento(
            telegram_id, "pelea",
            {
                "estilo": estilo, "resultado": resultado, "metodo": metodo,
                "peso_pesaje": peso_pesaje_kg, "rebound_pct": rebound_pct,
            },
        )
        return _ok({
            "estilo": estilo, "resultado": resultado, "metodo": metodo,
            "rebound_pct": rebound_pct, "alerta_rebound_alto": alerta_rebound,
            "round_final": round_final,
        })
    except Exception:
        logger.exception("Error en registrar_pelea")
        return _error("no pude registrar la pelea")


@function_tool
@_log_tool
async def calcular_peso_objetivo_responsable(
    telegram_id: int,
    peso_actual_kg: float,
    peso_categoria_kg: float,
    dias_hasta_pesaje: int,
    estilo_combate: str,
    nivel: str = "amateur",
) -> str:
    """Calcula plan de cut de peso responsable para combate (Reale 2017, IOC 2019).

    Devuelve plan dividido en cut cronico (peso real) + cut agudo (manipulacion).
    Activa red flag si: cut total > 8% en <14 dias O cut agudo > 5%.

    Args:
        telegram_id: ID Telegram
        peso_actual_kg: peso actual (40-200)
        peso_categoria_kg: limite de la categoria
        dias_hasta_pesaje: dias restantes (1-180)
        estilo_combate: boxeo, mma, bjj, muay_thai, kickboxing, judo, karate, taekwondo
        nivel: amateur o profesional
    """
    try:
        if not (40 <= peso_actual_kg <= 200):
            return _error("peso_actual fuera de rango")
        if not (40 <= peso_categoria_kg <= 200):
            return _error("peso_categoria fuera de rango")
        if not (1 <= dias_hasta_pesaje <= 180):
            return _error("dias_hasta_pesaje fuera de rango")
        if peso_actual_kg <= peso_categoria_kg:
            return _ok({
                "plan": "ya estas en categoria, no hay cut",
                "recomendacion": "mantenimiento + tecnica + S&C",
            })

        delta_kg = peso_actual_kg - peso_categoria_kg
        delta_pct = (delta_kg / peso_actual_kg) * 100

        if delta_pct > 8 and dias_hasta_pesaje < 14:
            return _ok({
                "alerta_critica": True,
                "mensaje": f"cut {delta_pct:.1f}% en {dias_hasta_pesaje} dias NO es responsable",
                "recomendacion": "subir de categoria o postergar pelea",
                "cita": "Reale 2017, IOC consensus 2019",
            })

        semanas = max(dias_hasta_pesaje / 7, 0.5)
        cut_cronico_max_kg = peso_actual_kg * 0.007 * semanas
        cut_cronico_aplicable = min(delta_kg, cut_cronico_max_kg)
        cut_agudo_aplicable = max(0.0, delta_kg - cut_cronico_aplicable)
        cut_agudo_pct = (cut_agudo_aplicable / peso_actual_kg) * 100

        if cut_agudo_pct > 5:
            return _ok({
                "alerta_critica": True,
                "mensaje": f"cut agudo necesario es {cut_agudo_pct:.1f}% > 5% maximo seguro",
                "recomendacion": "extender camp o subir de categoria",
                "cita": "Reale 2017",
            })

        await log_evento(
            telegram_id, "plan_cut",
            {"delta_pct": round(delta_pct, 2), "dias": dias_hasta_pesaje},
        )
        return _ok({
            "delta_total_kg": round(delta_kg, 2),
            "delta_pct": round(delta_pct, 2),
            "fase_cronica": {
                "duracion_dias": max(0, dias_hasta_pesaje - 7),
                "perdida_objetivo_kg": round(cut_cronico_aplicable, 2),
                "ritmo_sem_pct": "0.5-0.7%",
                "deficit_kcal_dia": 300 if cut_cronico_aplicable < 3 else 500,
                "proteina_g_kg": 2.2,
                "carbs_g_kg": 4.0,
                "grasa_g_kg": 0.8,
            },
            "fase_aguda": {
                "ventana_h": 24 if cut_agudo_pct <= 3 else 48,
                "perdida_objetivo_kg": round(cut_agudo_aplicable, 2),
                "perdida_pct": round(cut_agudo_pct, 2),
                "estrategia": [
                    "water loading -> water cut",
                    "low fiber 48h",
                    "glycogen depletion 36h",
                    "sodio reducido 24h",
                ],
                "advertencias": [
                    "NUNCA diureticos",
                    "NO sauna >20 min consecutivos",
                    "rehidratacion ORS post-pesaje OBLIGATORIA",
                ],
            },
            "cita_principal": "Reale R, Slater G, Burke LM. IJSPP 2017.",
            "recomendacion": "validar con nutricionista deportivo",
        })
    except Exception:
        logger.exception("Error en calcular_peso_objetivo_responsable")
        return _error("no pude calcular el plan")


@function_tool
@_log_tool
async def evaluar_concusion_simplificado(
    telegram_id: int,
    tuvo_perdida_conciencia: bool = False,
    duracion_perdida_seg: int = 0,
    nausea_vomito: bool = False,
    mareo_persistente: bool = False,
    confusion_amnesia: bool = False,
    dolor_cabeza_severo: bool = False,
    sensibilidad_luz_ruido: bool = False,
) -> str:
    """Triage SCAT6-simplificado post-golpe en cabeza (NO sustituye SCAT-6 oficial).

    Solo heuristica para derivacion. McCrory 2023 Amsterdam consensus, GRTP 6 etapas.

    Args:
        telegram_id: ID Telegram
        tuvo_perdida_conciencia: True si perdio el conocimiento
        duracion_perdida_seg: segundos perdidos (0 si no)
        nausea_vomito: True si presento nausea o vomito
        mareo_persistente: True si tiene mareo continuo
        confusion_amnesia: True si no recuerda eventos cercanos al golpe
        dolor_cabeza_severo: True si dolor de cabeza fuerte
        sensibilidad_luz_ruido: True si molesta luz/ruido
    """
    try:
        sintomas = sum([
            nausea_vomito, mareo_persistente, confusion_amnesia,
            dolor_cabeza_severo, sensibilidad_luz_ruido,
        ])

        if tuvo_perdida_conciencia and duracion_perdida_seg > 30:
            severidad, off_dias, rec = (
                "alta",
                21,
                "URGENCIAS hoy. Posible conmocion moderada-severa.",
            )
        elif tuvo_perdida_conciencia or sintomas >= 3:
            severidad, off_dias, rec = (
                "moderada",
                14,
                "Evaluacion medico deportivo <24h. Off sport.",
            )
        elif sintomas >= 1:
            severidad, off_dias, rec = (
                "baja-moderada",
                7,
                "Monitoreo 24h, off sport 7d min, evaluacion medica si empeora.",
            )
        else:
            severidad, off_dias, rec = (
                "minima",
                1,
                "Monitoreo 24-48h, off sport 24h preventivo.",
            )

        await log_evento(
            telegram_id, "screening_concusion",
            {"severidad": severidad, "sintomas": sintomas},
        )
        return _ok({
            "severidad": severidad,
            "off_sport_dias": off_dias,
            "recomendacion": rec,
            "sintomas_count": sintomas,
            "cita": "McCrory 2023 Amsterdam consensus, GRTP 6 etapas",
            "disclaimer": "Este triage NO sustituye evaluacion medica real",
        })
    except Exception:
        logger.exception("Error en evaluar_concusion_simplificado")
        return _error("no pude evaluar")


# ============================================================================
# Recordatorios personalizados
# ============================================================================


_DIAS_MAP = {
    "lun": 0, "lunes": 0, "mon": 0, "monday": 0,
    "mar": 1, "martes": 1, "tue": 1, "tuesday": 1,
    "mie": 2, "mié": 2, "miercoles": 2, "miércoles": 2, "wed": 2, "wednesday": 2,
    "jue": 3, "jueves": 3, "thu": 3, "thursday": 3,
    "vie": 4, "viernes": 4, "fri": 4, "friday": 4,
    "sab": 5, "sáb": 5, "sabado": 5, "sábado": 5, "sat": 5, "saturday": 5,
    "dom": 6, "domingo": 6, "sun": 6, "sunday": 6,
}


def _parse_dias_semana(raw: str) -> str:
    """Normaliza dias_semana a la forma '0,1,2,3,4,5,6'.

    Acepta "lun,mar,vie", "0,2,4", "diario", "todos", "L,M,V" o cadena vacia.
    Devuelve "" si es one-shot (sin dias).
    """
    if not raw:
        return ""
    s = raw.strip().lower()
    if s in {"diario", "todos", "todos_los_dias", "todos los dias", "daily", "everyday"}:
        return "0,1,2,3,4,5,6"
    if s in {"finde", "fin_de_semana", "fin de semana", "weekend"}:
        return "5,6"
    if s in {"laborales", "entre_semana", "entre semana", "weekdays"}:
        return "0,1,2,3,4"
    partes = [p.strip() for p in s.replace(";", ",").split(",") if p.strip()]
    dias: set[int] = set()
    for p in partes:
        if p.isdigit():
            n = int(p)
            if 0 <= n <= 6:
                dias.add(n)
            continue
        n = _DIAS_MAP.get(p)
        if n is not None:
            dias.add(n)
    return ",".join(str(d) for d in sorted(dias))


def _parse_hora(raw: str) -> dtime | None:
    """Parsea HH:MM 24h. Acepta "5:30", "05:30", "23:00"."""
    if not raw or ":" not in raw:
        return None
    try:
        hh, mm = raw.strip().split(":", 1)
        h, m = int(hh), int(mm[:2])
        if 0 <= h <= 23 and 0 <= m <= 59:
            return dtime(h, m)
    except (ValueError, IndexError):
        return None
    return None


@function_tool
@_log_tool
async def programar_recordatorio(
    telegram_id: int,
    mensaje: str,
    hora: str,
    dias_semana: str = "",
    fecha_unica: str = "",
) -> str:
    """Programa un recordatorio personalizado para el usuario.

    Casos de uso: "despiertame a las 5:30am", "recuerdame tomar creatina a las
    3pm de lunes a viernes", "recordatorio manana 7am de la cita". El bot
    enviara el mensaje a la hora indicada en la zona horaria del usuario.

    Args:
        telegram_id: ID de Telegram del usuario.
        mensaje: texto del recordatorio (ej: "Hora de entrenar!", "Toma creatina").
          Maximo 500 caracteres.
        hora: hora en formato HH:MM 24h en la zona horaria del usuario
          (ej "05:30", "15:00", "22:45").
        dias_semana: dias separados por coma (0=lun..6=dom). Tambien acepta
          "lun,mar,vie", "diario", "finde", "laborales". Vacio = one-shot.
        fecha_unica: fecha YYYY-MM-DD para recordatorio one-shot (ignorada si
          dias_semana esta definido). Vacio = manana si tampoco hay dias_semana.
    """
    try:
        if not mensaje or not mensaje.strip():
            return _error("mensaje vacio")
        t = _parse_hora(hora)
        if t is None:
            return _error("hora invalida, usa HH:MM 24h (ej 05:30)")
        dias = _parse_dias_semana(dias_semana)
        fecha: date | None = None
        if not dias:
            if fecha_unica.strip():
                try:
                    fecha = date.fromisoformat(fecha_unica.strip())
                except ValueError:
                    return _error("fecha_unica invalida, usa YYYY-MM-DD")
            else:
                fecha = (await _hoy_usuario(telegram_id)) + timedelta(days=1)

        rec = await repo_crear_recordatorio(
            telegram_id=telegram_id,
            mensaje=mensaje.strip(),
            hora=t,
            dias_semana=dias,
            fecha_unica=fecha,
        )
        if rec is None:
            return _error("no encontre tu usuario; manda /start primero")

        try:
            app = obtener_application()
            if app is not None and app.job_queue is not None:
                programar_recordatorio_en_jobqueue(app, rec)
        except Exception:
            logger.exception(
                "Recordatorio %s creado en DB pero no se pudo programar en JobQueue",
                rec.id,
            )

        await log_evento(
            telegram_id,
            "recordatorio_creado",
            {
                "id": rec.id,
                "hora": t.strftime("%H:%M"),
                "dias_semana": dias or "one-shot",
                "fecha_unica": fecha.isoformat() if fecha else None,
            },
        )
        return _ok({
            "id": rec.id,
            "mensaje": rec.mensaje,
            "hora": t.strftime("%H:%M"),
            "dias_semana": dias or "",
            "fecha_unica": fecha.isoformat() if fecha else None,
            "tz": rec.tz,
        })
    except Exception:
        logger.exception("Error en programar_recordatorio")
        return _error("no pude programar el recordatorio")


@function_tool
@_log_tool
async def listar_recordatorios(telegram_id: int) -> str:
    """Lista los recordatorios activos del usuario.

    Args:
        telegram_id: ID de Telegram del usuario.
    """
    try:
        recs = await repo_listar_recordatorios(telegram_id, solo_activos=True)
        items = [
            {
                "id": r.id,
                "mensaje": r.mensaje,
                "hora": r.hora.strftime("%H:%M") if r.hora else "",
                "dias_semana": r.dias_semana or "",
                "fecha_unica": r.fecha_unica.isoformat() if r.fecha_unica else None,
                "tz": r.tz,
            }
            for r in recs
        ]
        return _ok({"total": len(items), "recordatorios": items})
    except Exception:
        logger.exception("Error en listar_recordatorios")
        return _error("no pude listar tus recordatorios")


@function_tool
@_log_tool
async def cancelar_recordatorio(telegram_id: int, recordatorio_id: int) -> str:
    """Cancela (desactiva) un recordatorio del usuario por id.

    Args:
        telegram_id: ID de Telegram del usuario (validacion de ownership).
        recordatorio_id: id devuelto por listar_recordatorios.
    """
    try:
        ok = await repo_desactivar_recordatorio(recordatorio_id, telegram_id)
        if not ok:
            return _error("no existe ese recordatorio o no es tuyo")

        try:
            app = obtener_application()
            if app is not None and app.job_queue is not None:
                cancelar_recordatorio_jobs(app, recordatorio_id)
        except Exception:
            logger.exception(
                "Recordatorio %s desactivado en DB pero quedo el job activo",
                recordatorio_id,
            )

        await log_evento(
            telegram_id,
            "recordatorio_cancelado",
            {"id": recordatorio_id},
        )
        return _ok({"id": recordatorio_id, "cancelado": True})
    except Exception:
        logger.exception("Error en cancelar_recordatorio")
        return _error("no pude cancelar el recordatorio")
