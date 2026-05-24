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

from src.telegram.permissions import enforce_permissions

from src.db.repository import (
    actualizar_usuario,
    aceptar_modo_militar,
    cambiar_tono as repo_cambiar_tono,
    crear_compromiso,
    actualizar_sesion_skill_set as repo_actualizar_sesion_skill_set,
    crear_recordatorio as repo_crear_recordatorio,
    buscar_comida_similar as repo_buscar_comida_similar,
    cerrar_sesion_abierta as repo_cerrar_sesion_abierta,
    desactivar_recordatorio as repo_desactivar_recordatorio,
    eliminar_comida as repo_eliminar_comida,
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
    obtener_comidas_dia as repo_obtener_comidas_dia,
    obtener_compromiso_activo,
    obtener_o_crear_usuario,
    obtener_o_crear_streak,
    obtener_pr_ejercicio,
    obtener_ultima_sesion_skill as repo_obtener_ultima_sesion_skill,
    pausar_recordatorios,
    reporte_semanal,
    resumen_nutricional_dia,
    set_quiet_hours,
    usar_freeze_streak,
)
from src.db.repository import log_evento
from src.services.hidratacion import (
    consumo_hoy_ml,
    objetivo_ml,
    registrar_agua,
)
from src.telegram.bot_setup import obtener_application
from src.telegram.scheduler import (
    cancelar_recordatorio_jobs,
    programar_recordatorio_en_jobqueue,
)

from src.config import settings

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
        from src.telegram.permissions import current_turn_tools

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
            elapsed_ms = (time.perf_counter() - t0) * 1000
            ok = _looks_ok(result)

            # Registrar ejecución en el contexto asíncrono actual de la auditoría de turnos
            tools_list = current_turn_tools.get()
            if tools_list is not None:
                resumen_res = str(result)[:500] if result is not None else None
                tools_list.append({
                    "tool_name": tool_name,
                    "args": safe_args,
                    "kwargs": safe_kwargs,
                    "ok": ok,
                    "elapsed_ms": elapsed_ms,
                    "result_summary": resumen_res,
                    "error_info": None if ok else str(result)[:200]
                })

            log_fn = logger.info if ok else logger.warning
            log_fn(
                "tool.%s done ok=%s elapsed=%.1fms",
                tool_name,
                ok,
                elapsed_ms,
            )
            return result
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.exception(
                "tool.%s raised elapsed=%.1fms", tool_name, elapsed_ms
            )

            # Registrar fallo por excepción en el contexto de auditoría de turnos
            tools_list = current_turn_tools.get()
            if tools_list is not None:
                tools_list.append({
                    "tool_name": tool_name,
                    "args": safe_args,
                    "kwargs": safe_kwargs,
                    "ok": False,
                    "elapsed_ms": elapsed_ms,
                    "result_summary": None,
                    "error_info": f"{type(e).__name__}: {str(e)}"
                })
            raise

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
@enforce_permissions
async def obtener_perfil(telegram_id: int) -> str:
    """Obtiene perfil completo del usuario.

    Args:
        telegram_id: Telegram ID
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
    peso_estimado: bool = False,
) -> str:
    """Actualiza perfil. Solo envia campos con datos concretos.

    Args:
        telegram_id: Telegram ID
        nombre: nombre
        edad: anos
        peso_kg: kg
        altura_cm: cm
        objetivo: ganar_musculo|perder_grasa|mantenerse|mejorar_rendimiento
        nivel: principiante|intermedio|avanzado
        dias_entreno: dias/semana (1-7)
        deporte_principal: slug deporte (ver DeporteCatalogo)
        timezone: IANA tz (America/Bogota)
        pais: ISO 2 letras (CO, MX, AR, ES)
        onboarding_completo: True si peso+altura+objetivo+nivel+dias listos
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
        elif peso_estimado:
            kwargs["peso_kg"] = 70.0
            kwargs["peso_estimado"] = True
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
        if peso_estimado:
            kwargs["peso_estimado"] = True

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
@enforce_permissions
async def registrar_entreno(
    telegram_id: int,
    fecha: str,
    tipo: str,
    duracion_min: int = 60,
    ejercicios_json: str = "[]",
    rpe: float = 0,
    notas: str = "",
) -> str:
    """Registra entrenamiento e incrementa streak.

    Args:
        telegram_id: Telegram ID
        fecha: YYYY-MM-DD
        tipo: fuerza|cardio|movilidad|deporte
        duracion_min: minutos
        ejercicios_json: JSON array [{nombre,series,reps,peso_kg}]
        rpe: esfuerzo 1-10 (0=desconocido)
        notas: notas
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
    """Consulta PR de un ejercicio.

    Args:
        telegram_id: Telegram ID
        ejercicio: nombre del ejercicio
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
    """Registra nuevo PR.

    Args:
        telegram_id: Telegram ID
        ejercicio: nombre del ejercicio
        peso_kg: peso en kg
        reps: repeticiones con ese peso
        fecha: YYYY-MM-DD (vacio=hoy)
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
    """Lista todos los PRs del usuario.

    Args:
        telegram_id: Telegram ID
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
    """Registra comida con macros. Requiere alimentos NO vacios y al menos 1 macro>0.

    No llamar sin detalles; preguntar QUE comio primero. Detecta duplicados
    foto+texto automaticamente.

    Args:
        telegram_id: Telegram ID
        fecha: YYYY-MM-DD
        tipo: desayuno|almuerzo|cena|snack|post_entreno
        alimentos_json: JSON array de strings NO vacio
        calorias: kcal totales (>0 si macros=0)
        proteinas: g proteina
        carbs: g carbohidratos
        grasas: g grasa
    """
    try:
        tipo = tipo.lower().strip()
        if tipo not in TIPOS_COMIDA_VALIDOS:
            return _error(
                f"tipo invalido: {tipo}. Validos: {sorted(TIPOS_COMIDA_VALIDOS)}"
            )
        fecha_norm = _validar_fecha(fecha) if fecha else ""
        fecha_use = fecha_norm or (await _hoy_usuario(telegram_id)).isoformat()

        alimentos_raw = _safe_json_loads(alimentos_json, [])
        alimentos: list[str] = []
        for a in alimentos_raw:
            if isinstance(a, str) and a.strip():
                alimentos.append(a.strip()[:120])
            elif isinstance(a, dict):
                nombre = (
                    a.get("nombre") or a.get("name") or a.get("alimento") or ""
                )
                if isinstance(nombre, str) and nombre.strip():
                    alimentos.append(nombre.strip()[:120])
        if not alimentos:
            return _error(
                "alimentos requerido (lista no vacia). Pidele al usuario "
                "QUE comio antes de llamar esta tool."
            )

        macros_total = (proteinas or 0) + (carbs or 0) + (grasas or 0)
        if (calorias or 0) <= 0 and macros_total <= 0:
            return _error(
                "calorias y macros todos en 0. Estima los valores aproximados "
                "(ej: 2 huevos = 140 kcal P12g, 1 vaso leche = 150 kcal C12g G8g) "
                "o pide foto al usuario antes de llamar esta tool."
            )

        # Deteccion de duplicado: mismo (telegram_id, fecha, tipo) y alimentos
        # solapados >= 50%. Evita el patron foto+texto del mismo plato (un
        # registro y luego el usuario lo describe en texto).
        dup_id = await repo_buscar_comida_similar(
            telegram_id, fecha_use, tipo, alimentos
        )
        if dup_id is not None:
            logger.info(
                "registrar_comida duplicado detectado uid=%s tipo=%s "
                "existente_id=%s alimentos=%s",
                telegram_id, tipo, dup_id, alimentos[:5],
            )
            return _ok({
                "duplicado": True,
                "comida_existente_id": dup_id,
                "mensaje": (
                    f"ya hay una comida {tipo} con esos alimentos hoy "
                    f"(id={dup_id}); no inserto duplicado"
                ),
            })

        await repo_guardar_comida(
            telegram_id, fecha_use, tipo, alimentos, calorias, proteinas, carbs, grasas
        )
        await log_evento(
            telegram_id,
            "registro_comida",
            {
                "tipo": tipo,
                "fecha": fecha_use,
                "kcal": calorias,
                "n_alimentos": len(alimentos),
            },
        )
        return _ok({
            "tipo": tipo,
            "fecha": fecha_use,
            "alimentos": alimentos,
            "calorias": calorias,
            "proteinas_g": proteinas,
            "carbs_g": carbs,
            "grasas_g": grasas,
        })
    except Exception:
        logger.exception("Error en registrar_comida")
        return _error("no pude registrar la comida")


@function_tool
@_log_tool
async def registrar_hidratacion(telegram_id: int, ml: int) -> str:
    """Registra el consumo de agua en mililitros.

    Args:
        telegram_id: ID de Telegram del usuario.
        ml: cantidad de agua en mililitros (ej: 250, 500).
    """
    try:
        await registrar_agua(telegram_id, ml)
        await log_evento(telegram_id, "registrar_hidratacion", {"ml": ml})
        return json.dumps({"ok": True, "mensaje": f"Registrados {ml}ml de agua."})
    except Exception:
        logger.exception("Error en registrar_hidratacion")
        return json.dumps({"ok": False, "error": "No pude registrar el agua."})


@function_tool
@_log_tool
async def consultar_hidratacion_hoy(telegram_id: int) -> str:
    """Consulta el consumo de agua de hoy y el objetivo diario.

    Args:
        telegram_id: ID de Telegram del usuario.
    """
    try:
        consumo = await consumo_hoy_ml(telegram_id)
        objetivo = await objetivo_ml(telegram_id)
        return json.dumps({
            "ok": True,
            "consumo_hoy_ml": consumo,
            "objetivo_diario_ml": objetivo,
            "faltante_ml": max(0, objetivo - consumo),
            "porcentaje": round((consumo / objetivo * 100), 1) if objetivo > 0 else 0
        })
    except Exception:
        logger.exception("Error en consultar_hidratacion_hoy")
        return json.dumps({"ok": False, "error": "No pude consultar la hidratacion."})


@function_tool
@_log_tool
async def resumen_nutricional(telegram_id: int, fecha: str = "") -> str:
    """Resumen calorias y macros de un dia.

    Args:
        telegram_id: Telegram ID
        fecha: YYYY-MM-DD (vacio=hoy)
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
    """Registra sueno. Requiere horas>0; no inventar, preguntar al usuario.

    Args:
        telegram_id: Telegram ID
        fecha: YYYY-MM-DD (fecha en que desperto)
        horas: horas dormidas (1-16). No llamar si desconocido.
        calidad: 1=pesimo 2=malo 3=normal 4=bueno 5=excelente
        notas: notas
    """
    try:
        if horas is None or horas <= 0:
            return _error(
                "horas requerido (1-16). Pidele al usuario cuantas horas durmio "
                "antes de llamar esta tool."
            )
        if horas > 16:
            return _error(
                "horas fuera de rango (max 16). Verifica el dato con el usuario."
            )
        fecha_norm = _validar_fecha(fecha) if fecha else ""
        fecha_use = fecha_norm or (await _hoy_usuario(telegram_id)).isoformat()
        calidad = max(1, min(5, calidad))
        await repo_guardar_sueno(telegram_id, fecha_use, horas, calidad, notas)
        await log_evento(
            telegram_id,
            "registro_sueno",
            {"horas": horas, "calidad": calidad, "fecha": fecha_use},
        )
        return _ok({"horas": horas, "calidad": calidad, "fecha": fecha_use})
    except Exception:
        logger.exception("Error en registrar_sueno")
        return _error("no pude registrar el sueno")


@function_tool
@_log_tool
async def reporte_progreso(telegram_id: int) -> str:
    """Reporte semanal: sesiones, volumen, PRs y sueno (7 dias).

    Args:
        telegram_id: Telegram ID
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
        telegram_id: Telegram ID
        peso_kg: peso en kg
        grasa_pct: % grasa corporal (0=desconocido)
        cintura_cm: cintura en cm (0=desconocido)
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
    """Ultimos registros de peso.

    Args:
        telegram_id: Telegram ID
        limit: max registros (default 10)
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
    """Firma compromiso con objetivo. El bot lo citara si falla.

    Args:
        telegram_id: Telegram ID
        objetivo_texto: objetivo en 1a persona
        deadline: YYYY-MM-DD limite
        frecuencia_semanal: dias/semana (1-7)
        tipo_compromiso: entreno|comida|peso|general
        stake_simbolico: que pierde si falla
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
    """Devuelve compromiso activo e incrementa citado_veces.

    Args:
        telegram_id: Telegram ID
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
    """Cambia tono del coach. Militar requiere disclaimer aceptado.

    Args:
        telegram_id: Telegram ID
        tono: amigable|firme|militar
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
    """Marca aceptacion disclaimer militar. Solo tras confirmacion explicita.

    Args:
        telegram_id: Telegram ID
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
    """Configura horas de silencio (sin notificaciones).

    Args:
        telegram_id: Telegram ID
        hora_inicio: HH:MM 24h
        hora_fin: HH:MM 24h
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
    """Pausa recordatorios por N dias.

    Args:
        telegram_id: Telegram ID
        dias: dias de pausa (1-30)
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
    """Usa 1 freeze para no romper streak hoy.

    Args:
        telegram_id: Telegram ID
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
    """Consulta streak actual.

    Args:
        telegram_id: Telegram ID
        tipo: entreno|comida|sueno|peso|todos
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


@function_tool
@_log_tool
async def consultar_desafio_dia(telegram_id: int) -> str:
    """Consulta desafío diario de cohorte: meta, progreso y posición.

    Args:
        telegram_id: Telegram ID del usuario
    """
    from src.services.comunidad import estado_desafio_usuario, usuario_tiene_opt_in
    from src.services.desafios.cohorte import cohorte_key_usuario
    from src.db.repository import obtener_usuario

    try:
        opt_in = await usuario_tiene_opt_in(telegram_id)
        user = await obtener_usuario(telegram_id)
        cohorte = cohorte_key_usuario(user) if user else "desconocido"
        if not opt_in:
            return json.dumps(
                {
                    "opt_in": False,
                    "cohorte": cohorte,
                    "mensaje": "Activa desafíos con /desafios",
                }
            )
        estado = await estado_desafio_usuario(telegram_id)
        if estado is None or estado.get("desafio") is None:
            return json.dumps(
                {
                    "opt_in": True,
                    "cohorte": cohorte,
                    "desafio": None,
                    "mensaje": "Sin desafío de cohorte hoy todavía",
                }
            )
        d = estado["desafio"]
        return json.dumps(
            {
                "opt_in": True,
                "cohorte": cohorte,
                "titulo": d.titulo,
                "metrica": d.metrica,
                "meta": d.meta_valor,
                "progreso": estado.get("valor", 0),
                "posicion": estado.get("posicion"),
                "inscrito": estado.get("inscrito", False),
            }
        )
    except Exception:
        logger.exception("Error en consultar_desafio_dia")
        return _error("no pude consultar el desafío del día")


# ============================================================================
# Engagement (Fase 5/6/7)
# ============================================================================


@function_tool
@_log_tool
async def proponer_ejercicio_aleatorio(telegram_id: int) -> str:
    """Sortea foco de ejercicio para hoy.

    Args:
        telegram_id: Telegram ID
    """
    opciones = ["push", "pull", "piernas", "core + cardio", "movilidad activa", "descanso activo"]
    eleccion = random.choice(opciones)
    await log_evento(telegram_id, "rueda_ejercicio", {"eleccion": eleccion})
    return _ok({"foco_propuesto": eleccion, "mensaje": f"Hoy toca: {eleccion}"})


@function_tool
@_log_tool
async def dar_premio_motivacional(telegram_id: int) -> str:
    """Otorga mensaje motivacional aleatorio.

    Args:
        telegram_id: Telegram ID
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
    """Verifica hito streak (7/30/100/365). Llamar post registrar_entreno.

    Args:
        telegram_id: Telegram ID
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
    """Info para generar chart visual de progreso.

    Args:
        telegram_id: Telegram ID
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
    """Registra truco aterrizado (urbano). Primer aterrizaje crea PR.

    Args:
        telegram_id: Telegram ID
        deporte: skate|bmx|rollers|parkour|scooter
        nombre_truco: nombre del truco (max 80 chars)
        spot: lugar
        video_url: URL clip
        intentos: intentos hasta lograrlo
        es_primer_aterrizaje: True=primer aterrizaje (crea PR)
        fecha: YYYY-MM-DD (vacio=hoy)
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
    """Registra sesion skill sport (no gym). Caidas>=3 o sensacion<=2 activan alerta.

    Args:
        telegram_id: Telegram ID
        deporte: skate|bmx|rollers|parkour|scooter
        duracion_min: minutos (5-480)
        spot: lugar
        foco_sesion: foco de la sesion
        trucos_intentados: cantidad intentados
        trucos_aterrizados: cantidad aterrizados
        num_caidas: caidas notables (>2=bandera)
        sensacion_1_5: 1=pesimo 5=excelente
        co_riders: companeros separados por coma
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
    """Registra via/boulder escalada. Lesion dedo activa alerta crimping.

    Args:
        telegram_id: Telegram ID
        nombre_via: nombre via o boulder
        grado: YDS (5.10a)|Fontainebleau (V4)|francesa (6c)
        spot: lugar
        estilo: on_sight|flash|redpoint|repunto|proyecto|boulder
        intentos: intentos hasta enviarla
        lesion_dedo_si_no: True si dolor en dedos
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
    """Resumen progreso skill: sesiones + trucos (no kg).

    Args:
        telegram_id: Telegram ID
        deporte: skate|bmx|rollers|parkour|scooter
        ventana_dias: ventana analisis (7-365, default 30)
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
    """Registra sparring. Golpe cabeza activa screening concusion.

    Args:
        telegram_id: Telegram ID
        estilo: boxeo|bjj|mma|muay_thai|kickboxing|wrestling|judo|karate|taekwondo|capoeira|krav_maga
        rounds: rounds o rolls
        duracion_round_min: min/round
        intensidad_1_10: 1-3 light, 4-6 medium, 7-10 hard
        golpe_cabeza_fuerte: True=screening concusion
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
    """Registra pelea oficial. Calcula rebound pesaje vs dia pelea.

    Args:
        telegram_id: Telegram ID
        estilo: boxeo|mma|muay_thai|bjj|kickboxing|wrestling
        resultado: ganada|perdida|draw|no_contest|dq
        metodo: ko|tko|decision_unanime|decision_dividida|decision_mayoritaria|sumision|dq|draw
        peso_pesaje_kg: peso oficial pesaje (40-200)
        peso_dia_pelea_kg: peso dia pelea (mide rebound)
        opponent_record: record oponente
        round_final: round final (0=decision)
        spot: lugar/evento
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
    """Plan cut peso responsable (Reale 2017, IOC 2019). Red flag si >8%/<14d.

    Args:
        telegram_id: Telegram ID
        peso_actual_kg: peso actual (40-200)
        peso_categoria_kg: limite categoria
        dias_hasta_pesaje: dias restantes (1-180)
        estilo_combate: boxeo|mma|bjj|muay_thai|kickboxing|judo|karate|taekwondo
        nivel: amateur|profesional
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
@enforce_permissions
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
    """Triage SCAT6-simplificado post-golpe cabeza. No sustituye evaluacion medica.

    Args:
        telegram_id: Telegram ID
        tuvo_perdida_conciencia: perdio conocimiento
        duracion_perdida_seg: segundos inconsciente (0=no)
        nausea_vomito: nausea o vomito
        mareo_persistente: mareo continuo
        confusion_amnesia: no recuerda eventos del golpe
        dolor_cabeza_severo: dolor cabeza fuerte
        sensibilidad_luz_ruido: molesta luz/ruido
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
    """Programa recordatorio personalizado.

    Args:
        telegram_id: Telegram ID
        mensaje: texto del recordatorio (max 500 chars)
        hora: HH:MM 24h (tz del usuario)
        dias_semana: 0=lun..6=dom csv, o diario|finde|laborales (vacio=one-shot)
        fecha_unica: YYYY-MM-DD one-shot (ignorada si dias_semana, vacio=manana)
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

            tz = await _tz_usuario(telegram_id)
            ahora_local = datetime.now(tz)
            when_local = datetime.combine(fecha, t, tzinfo=tz)
            if when_local <= ahora_local:
                return json.dumps({
                    "ok": False,
                    "error": "La hora especificada ya pasó para hoy. Por favor programar a una hora futura."
                })

        rec = await repo_crear_recordatorio(
            telegram_id=telegram_id,
            mensaje=mensaje.strip(),
            hora=t,
            dias_semana=dias,
            fecha_unica=fecha,
        )
        if rec is None:
            return _error("no encontre tu usuario; manda /start primero")

        if settings.use_redis_task_queue:
            from src.tasks.scheduling import schedule_recordatorio_task

            await schedule_recordatorio_task(rec)
        else:
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
    """Lista recordatorios activos.

    Args:
        telegram_id: Telegram ID
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
    """Cancela recordatorio por id.

    Args:
        telegram_id: Telegram ID (valida ownership)
        recordatorio_id: id de listar_recordatorios
    """
    try:
        ok = await repo_desactivar_recordatorio(recordatorio_id, telegram_id)
        if not ok:
            return _error("no existe ese recordatorio o no es tuyo")

        if settings.use_redis_task_queue:
            from src.tasks.queue import cancel_tasks

            await cancel_tasks(telegram_id, task_type="recordatorio")
        else:
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


@function_tool
@_log_tool
async def listar_tareas_programadas(telegram_id: int) -> str:
    """Lista tareas pendientes en la cola (recordatorios, escalacion, hidratacion).

    Args:
        telegram_id: Telegram ID
    """
    try:
        if not settings.use_redis_task_queue:
            recs = await repo_listar_recordatorios(telegram_id, solo_activos=True)
            return _ok({
                "fuente": "postgres_recordatorios",
                "total": len(recs),
                "tareas": [
                    {
                        "type": "recordatorio",
                        "mensaje": r.mensaje,
                        "hora": r.hora.strftime("%H:%M") if r.hora else "",
                        "id": r.id,
                    }
                    for r in recs
                ],
            })
        from src.tasks.queue import list_tasks

        tasks = await list_tasks(telegram_id)
        items = []
        for t in tasks:
            run_at = t.get("run_at", 0)
            items.append({
                "id": t.get("id"),
                "type": t.get("type"),
                "status": t.get("status"),
                "run_at_unix": run_at,
                "payload": t.get("payload"),
            })
        return _ok({"fuente": "redis", "total": len(items), "tareas": items})
    except Exception:
        logger.exception("Error en listar_tareas_programadas")
        return _error("no pude listar tus tareas programadas")


@function_tool
@_log_tool
async def cerrar_sesion_entrenamiento(
    telegram_id: int,
    sesion_id: int = 0,
) -> str:
    """Cierra sesion en curso. Evita duplicados en mensajes consecutivos.

    Args:
        telegram_id: Telegram ID (valida ownership)
        sesion_id: id a cerrar (0=ultima abierta hoy)
    """
    try:
        sid = sesion_id if sesion_id > 0 else None
        sesion = await repo_cerrar_sesion_abierta(telegram_id, sid)
        if sesion is None:
            return _error("no hay sesion abierta para cerrar")
        await log_evento(
            telegram_id,
            "sesion_cerrada",
            {
                "sesion_id": sesion.id,
                "duracion_min": sesion.duracion_min,
                "deporte": sesion.deporte_slug,
            },
        )
        return _ok({
            "sesion_id": sesion.id,
            "cerrada": True,
            "duracion_min": sesion.duracion_min,
            "deporte": sesion.deporte_slug,
        })
    except Exception:
        logger.exception("Error en cerrar_sesion_entrenamiento")
        return _error("no pude cerrar la sesion")


@function_tool
@_log_tool
async def consultar_ultima_sesion_skill(
    telegram_id: int, deporte: str = ""
) -> str:
    """Ultima sesion skill de hoy. Usar antes de editar_sesion_reciente.

    Args:
        telegram_id: Telegram ID
        deporte: slug deporte (vacio=cualquiera)
    """
    try:
        deporte_f = deporte.strip().lower() or None
        sesion = await repo_obtener_ultima_sesion_skill(telegram_id, deporte_f)
        if sesion is None:
            return _ok({"existe": False})
        return _ok({
            "existe": True,
            "sesion_id": sesion.id,
            "fecha": sesion.fecha.isoformat() if sesion.fecha else None,
            "deporte": sesion.deporte_slug,
            "duracion_min": sesion.duracion_min,
            "trucos_intentados": sesion.trucos_intentados,
            "trucos_aterrizados": sesion.trucos_aterrizados,
            "num_caidas": sesion.num_caidas,
            "sensacion_1_5": sesion.sensacion_1_5,
            "foco_sesion": sesion.foco_sesion,
            "spot": sesion.spot,
            "notas": sesion.notas,
            "cerrada": sesion.cerrada,
            "updated_at": (
                sesion.updated_at.isoformat() if sesion.updated_at else None
            ),
        })
    except Exception:
        logger.exception("Error en consultar_ultima_sesion_skill")
        return _error("no pude consultar la sesion")


@function_tool
@_log_tool
async def editar_sesion_reciente(
    telegram_id: int,
    sesion_id: int = 0,
    deporte: str = "",
    duracion_min: int = -1,
    trucos_intentados: int = -1,
    trucos_aterrizados: int = -1,
    num_caidas: int = -1,
    sensacion_1_5: int = -1,
    foco_sesion: str = "",
    notas: str = "",
) -> str:
    """Corrige campos sesion con SET (reemplaza, no suma). Solo hoy.

    -1=no tocar (enteros), ""=no tocar (strings).

    Args:
        telegram_id: Telegram ID (valida ownership)
        sesion_id: id especifico (0=ultima del dia)
        deporte: slug deporte para filtrar
        duracion_min: minutos (-1=no tocar)
        trucos_intentados: total absoluto (-1=no tocar)
        trucos_aterrizados: total absoluto (-1=no tocar)
        num_caidas: total absoluto (-1=no tocar)
        sensacion_1_5: 1-5 (-1=no tocar)
        foco_sesion: foco (""=no tocar)
        notas: notas completas (""=no tocar)
    """
    try:
        campos: dict = {}
        if duracion_min >= 0:
            campos["duracion_min"] = duracion_min
        if trucos_intentados >= 0:
            campos["trucos_intentados"] = trucos_intentados
        if trucos_aterrizados >= 0:
            campos["trucos_aterrizados"] = trucos_aterrizados
        if num_caidas >= 0:
            campos["num_caidas"] = num_caidas
        if sensacion_1_5 >= 0:
            campos["sensacion_1_5"] = max(1, min(5, sensacion_1_5))
        if foco_sesion.strip():
            campos["foco_sesion"] = foco_sesion.strip()
        if notas.strip():
            campos["notas"] = notas.strip()
        if not campos:
            return _error(
                "no hay campos a editar (todos quedaron en -1 o vacios)"
            )

        sid = sesion_id if sesion_id > 0 else None
        deporte_f = deporte.strip().lower() or None
        sesion = await repo_actualizar_sesion_skill_set(
            telegram_id=telegram_id,
            sesion_id=sid,
            deporte=deporte_f,
            **campos,
        )
        if sesion is None:
            return _error(
                "no encontre sesion para editar (o no es de hoy)"
            )
        await log_evento(
            telegram_id,
            "sesion_editada",
            {
                "sesion_id": sesion.id,
                "campos_editados": list(campos.keys()),
            },
        )
        return _ok({
            "sesion_id": sesion.id,
            "actualizada": True,
            "duracion_min": sesion.duracion_min,
            "trucos_intentados": sesion.trucos_intentados,
            "trucos_aterrizados": sesion.trucos_aterrizados,
            "num_caidas": sesion.num_caidas,
            "sensacion_1_5": sesion.sensacion_1_5,
        })
    except Exception:
        logger.exception("Error en editar_sesion_reciente")
        return _error("no pude editar la sesion")


@function_tool
@_log_tool
@enforce_permissions
async def eliminar_comida_reciente(
    telegram_id: int, comida_id: int = 0, tipo: str = ""
) -> str:
    """Borra una comida de HOY. Requiere comida_id o tipo.

    Args:
        telegram_id: Telegram ID
        comida_id: id especifico (0=no usa)
        tipo: desayuno|almuerzo|cena|snack|post_entreno (borra mas reciente)
    """
    try:
        cid = comida_id if comida_id > 0 else None
        tipo_norm = tipo.strip().lower() or None
        if cid is None and tipo_norm is None:
            return _error(
                "necesito comida_id o tipo (desayuno/almuerzo/cena/snack)"
            )
        if tipo_norm and tipo_norm not in TIPOS_COMIDA_VALIDOS:
            return _error(
                f"tipo invalido: {tipo}. Validos: {sorted(TIPOS_COMIDA_VALIDOS)}"
            )
        borrado_id = await repo_eliminar_comida(
            telegram_id=telegram_id,
            comida_id=cid,
            tipo=tipo_norm,
        )
        if borrado_id is None:
            return _error("no encontre comida para borrar (o no es de hoy)")
        await log_evento(
            telegram_id,
            "comida_eliminada",
            {"comida_id": borrado_id, "tipo": tipo_norm},
        )
        return _ok({"comida_id": borrado_id, "eliminada": True})
    except Exception:
        logger.exception("Error en eliminar_comida_reciente")
        return _error("no pude eliminar la comida")
