"""Handlers de Telegram: comandos, mensajes, callbacks, foto."""
from __future__ import annotations

import asyncio
import html as _html
import logging
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import openai
import telegram.error
from telegram import (
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestChat,
    LabeledPrice,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from agents import (
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    RunConfig,
    Runner,
    SessionSettings,
)

from src.cache import (
    get_perfil_block as cache_get_perfil_block,
    limpiar_keys_usuario,
    set_perfil_block as cache_set_perfil_block,
)
from src.telegram.safe_session import SafeRedisSession
from src.coach import coach
from src.config import settings
from src.db.models import PlanSuscripcion
from src.services.crisis import detectar as detectar_crisis
from src.services.crisis import detectar_diagnostico_output
from src.db.models import DuracionPago
from src.db.repository import (
    actualizar_usuario,
    aceptar_modo_militar,
    activar_plan,
    cambiar_tono as repo_cambiar_tono,
    contar_fotos_hoy,
    eliminar_usuario,
    guardar_comida,
    guardar_comprobante,
    guardar_feedback_comida,
    log_crisis,
    log_evento,
    log_llm_usage,
    marcar_bot_bloqueado,
    marcar_comprobante_duplicado,
    obtener_compromiso_activo,
    obtener_o_crear_usuario,
    obtener_o_crear_streak,
    obtener_usuario,
    obtener_plan_actual,
    pausar_recordatorios,
    set_quiet_hours,
    ultimos_eventos,
    usar_freeze_streak,
)
from src.services.hidratacion import consumo_hoy_ml, objetivo_ml
from src.telegram.decoradores import requiere_tier
from src.telegram.middlewares import check_daily_quota, check_rate_limit
from src.telegram.reacciones import reaccionar

logger = logging.getLogger(__name__)

RUN_CONFIG = RunConfig(session_settings=SessionSettings(limit=settings.session_limit))


# Reply keyboard persistente con los 12 accesos mas usados. Cada texto se
# captura por `mensaje()` (REPLY_KEYBOARD_INTENTS) y se traduce a un prompt
# claro para el coach o un comando directo.
QUICK_ACTIONS_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("Entrene"), KeyboardButton("Comi"), KeyboardButton("Dormi")],
        [KeyboardButton("Peso"), KeyboardButton("Agua"), KeyboardButton("Calma")],
        [KeyboardButton("Plan de hoy"), KeyboardButton("Mi semana"), KeyboardButton("Mis PRs")],
        [KeyboardButton("Recordatorios"), KeyboardButton("Compromiso"), KeyboardButton("Tono")],
    ],
    is_persistent=True,
    resize_keyboard=True,
    input_field_placeholder="Escribi o tap",
)


class _FakeUpdate:
    """Wrapper minimo para reutilizar `cmd_*(update, ctx)` desde callbacks.

    Los handlers existentes esperan `update.message.reply_text` y
    `update.effective_user.id`. Cuando viene un callback_query queremos
    redirigir a esos handlers sin duplicar codigo. OJO: `q.message.from_user`
    es el BOT (porque el mensaje lo envio el bot); el usuario real esta en
    `q.from_user`. Por eso recibimos ambos explicitamente.
    """

    __slots__ = ("message", "effective_user", "effective_chat", "callback_query")

    def __init__(self, message, user):
        self.message = message
        self.effective_user = user
        self.effective_chat = message.chat if message else None
        self.callback_query = None


# Mapa de etiquetas del reply keyboard -> prompts que el coach recibe.
# Usamos prompts naturales para que el coach use las tools correctas.
# Algunas etiquetas (Tono, Agua, Calma) usan comandos slash internos para
# disparar el handler dedicado en vez de pasar por el LLM.
REPLY_KEYBOARD_INTENTS: dict[str, str] = {
    "Entrene": "Quiero registrar mi entrenamiento de hoy",
    "Comi": "Quiero registrar lo que comi",
    "Dormi": "Quiero registrar como dormi",
    "Peso": "Quiero registrar mi peso actual",
    "Plan de hoy": "Dame mi plan de hoy: entreno, comida y agua",
    "Mi semana": "Dame mi reporte semanal completo (entrenos, sueno, comidas)",
    "Mis PRs": "Muestrame mis Personal Records actuales",
    "Recordatorios": "Lista mis recordatorios activos",
    "Compromiso": "Quiero ver mi compromiso firmado",
    "Tono": "Quiero cambiar el tono del coach",
    "Agua": "Quiero registrar agua y ver como voy hoy",
    "Calma": "Necesito 3 min de respiracion guiada",
}


_CONFIRMACION_ENTRENO = re.compile(
    r"\b(entren[ée]|listo|hecho|termin[eé]|ya\s+lo\s+hice|complet[eé]|hice\s+pierna|"
    r"hice\s+pecho|hice\s+espalda|hice\s+brazo)\b",
    re.IGNORECASE,
)


async def _enviar_con_retry(message, texto: str, intentos: int = 3, **kwargs) -> None:
    """Envia un mensaje con retry exponencial. Marca bot_bloqueado en Forbidden."""
    for i in range(intentos):
        try:
            await message.reply_text(texto, **kwargs)
            return
        except telegram.error.TimedOut:
            if i == intentos - 1:
                raise
            await asyncio.sleep(1.5**i)
        except telegram.error.RetryAfter as e:
            await asyncio.sleep(e.retry_after)
            if i == intentos - 1:
                raise
        except telegram.error.Forbidden:
            uid = getattr(message.chat, "id", None)
            if uid is not None:
                await marcar_bot_bloqueado(uid, True)
            logger.info("Bot bloqueado por uid=%s", uid)
            return


_SAFE_TAGS_RE = re.compile(r'</?(?:b|i|code|pre|blockquote)(?:\s[^>]*)?>')


def _sanitize_telegram_html(text: str) -> str:
    """Escapa HTML del output LLM, preservando solo tags seguros de Telegram."""
    parts: list[str] = []
    last = 0
    for m in _SAFE_TAGS_RE.finditer(text):
        parts.append(_html.escape(text[last:m.start()]))
        parts.append(m.group())
        last = m.end()
    parts.append(_html.escape(text[last:]))
    return "".join(parts)


async def _build_prompt(texto: str, uid: int) -> str:
    """Construye el prompt con perfil + tono + compromiso + streak inyectados.

    Inyecta `fecha`, `hora_actual` y `tz` calculados en la zona horaria del
    usuario (no del servidor) para que el LLM pueda resolver intenciones tipo
    "en N minutos", "esta noche", "manana 8am" sin equivocarse.

    La parte estatica del bloque (todo menos hora_actual y tono dinamicos)
    se cachea en Redis con TTL=30s via `cache.get_perfil_block`. Esto baja
    las 3 queries DB por turno a 0 en mensajes consecutivos. La hora se
    siempre recalcula (cambia cada minuto).
    """
    cached_static = await cache_get_perfil_block(uid)
    user = await obtener_o_crear_usuario(uid)
    tz_name = user.timezone or "America/Bogota"
    try:
        ahora_user = datetime.now(ZoneInfo(tz_name))
    except Exception:
        tz_name = "America/Bogota"
        ahora_user = datetime.now(ZoneInfo(tz_name))
    hoy_user = ahora_user.date()

    # Hidratacion hoy
    agua_hoy = await consumo_hoy_ml(uid)
    agua_obj = await objetivo_ml(uid)

    dinamicos = [
        f"uid={uid}",
        f"fecha={hoy_user.isoformat()}",
        f"hora_actual={ahora_user.strftime('%H:%M')}",
        f"tz={tz_name}",
        f"tono={user.tono.value if user.tono else 'firme'}",
        f"pais={user.pais or 'CO'}",
        f"agua_hoy={agua_hoy}ml",
        f"agua_objetivo={agua_obj}ml",
    ]
    if cached_static is not None:
        return f"[{' | '.join(dinamicos)} | {cached_static}] {texto}"

    def _sanitize(v: str) -> str:
        return re.sub(r'[\[\]|{}<>]', '', v)[:80]

    estaticos = []
    if user.nombre:
        estaticos.append(f"nombre={_sanitize(user.nombre)}")
    if user.peso_kg:
        estaticos.append(f"peso={user.peso_kg}kg")
    if user.altura_cm:
        estaticos.append(f"altura={user.altura_cm}cm")
    if user.edad:
        estaticos.append(f"edad={user.edad}")
    if user.objetivo:
        estaticos.append(f"objetivo={_sanitize(user.objetivo)}")
    if user.nivel:
        estaticos.append(f"nivel={_sanitize(user.nivel)}")
    if user.dias_entreno:
        estaticos.append(f"dias_entreno={user.dias_entreno}")
    if user.deporte_principal:
        estaticos.append(f"deporte={_sanitize(user.deporte_principal)}")
    if user.categoria_deporte:
        estaticos.append(f"categoria_deporte={user.categoria_deporte.value}")
    if user.modalidad_deporte:
        estaticos.append(f"modalidad={_sanitize(user.modalidad_deporte)}")
    if user.es_competitivo:
        estaticos.append("competitivo=si")
    estaticos.append(
        f"onboarding={'si' if user.onboarding_completo else 'no'}"
    )
    compromiso = await obtener_compromiso_activo(uid)
    if compromiso:
        estaticos.append(
            f"compromiso='{compromiso.objetivo_texto[:80]}' (deadline={compromiso.deadline.isoformat()})"
        )
    try:
        streak = await obtener_o_crear_streak(uid, "entreno")
        estaticos.append(f"streak_entreno={streak.dias_actuales}")
    except Exception:
        pass
    if user.pausado_hasta and user.pausado_hasta >= hoy_user:
        estaticos.append(f"pausado_hasta={user.pausado_hasta.isoformat()}")
    estatico_block = " | ".join(estaticos)
    await cache_set_perfil_block(uid, estatico_block)
    return f"[{' | '.join(dinamicos)} | {estatico_block}] {texto}"


async def _procesar(
    message,
    texto: str,
    uid: int,
    with_keyboard: bool = False,
    ctx: ContextTypes.DEFAULT_TYPE | None = None,
) -> None:
    """Ejecuta el agente con sesion Redis. Sesion DB cerrada antes del LLM.
    Cancela escalation de los tipos que el usuario cumplio during the run.
    """
    import time
    import uuid
    from src.telegram.permissions import current_session_uid, current_turn_tools
    from src.db.repository import grabar_auditoria_turno

    t_start = time.perf_counter()
    request_id = uuid.uuid4().hex

    # Variables de recopilación de auditoría
    prompt_usuario = texto
    respuesta_bot = None
    tokens_input = 0
    tokens_output = 0
    costo_estimado = 0.0
    error_message = None

    token = current_session_uid.set(uid)
    token_tools = current_turn_tools.set([])

    try:
        prompt = await _build_prompt(texto, uid)
        session = SafeRedisSession.from_url(
            str(uid),
            url=settings.redis_url_str,
            ttl=settings.session_ttl_seconds,
        )
        try:
            try:
                result = await Runner.run(
                    coach, prompt, session=session, run_config=RUN_CONFIG
                )
                output = result.final_output

                if result.raw_responses:
                    try:
                        total_in = sum(r.usage.input_tokens for r in result.raw_responses if r.usage)
                        total_out = sum(r.usage.output_tokens for r in result.raw_responses if r.usage)
                        tokens_input = total_in
                        tokens_output = total_out
                        costo_estimado = (total_in / 1_000_000) * 0.15 + (total_out / 1_000_000) * 0.60
                        if settings.coach_model in ("gpt-4o", "gpt-4"):
                            costo_estimado = (total_in / 1_000_000) * 2.50 + (total_out / 1_000_000) * 10.00
                        await log_llm_usage(uid, "coach", settings.coach_model, total_in, total_out, rounds=len(result.raw_responses))
                    except Exception:
                        pass

                diag = detectar_diagnostico_output(output)
                if diag:
                    logger.warning("Output guardrail (regex fallback): diagnostico uid=%s: %s", uid, diag)
                    output = (
                        "Note algo en mi respuesta que prefiero no afirmar. Lo correcto es "
                        "que un profesional medico/nutricionista/psicologo evalue tu caso. "
                        "Sigamos con habitos concretos: que vamos a hacer hoy?"
                    )
                    await log_evento(uid, "output_guardrail_diagnostico", {"matches": diag[:5]})

                respuesta_bot = output
                output_sanitized = _sanitize_telegram_html(output)
                chunks = [output_sanitized[i : i + 4000] for i in range(0, len(output_sanitized), 4000)] or [""]
                for i, chunk in enumerate(chunks):
                    kwargs = {}
                    if with_keyboard and i == len(chunks) - 1:
                        kwargs["reply_markup"] = QUICK_ACTIONS_KEYBOARD
                    await _enviar_con_retry(message, chunk, **kwargs)

                if ctx is not None and ctx.job_queue is not None:
                    await _autocancelar_escalation_si_cumplio(uid, ctx)

            except InputGuardrailTripwireTriggered as e:
                guardrail_obj = getattr(getattr(e, "guardrail_result", None), "guardrail", None)
                g_name = getattr(guardrail_obj, "name", "")
                logger.warning("Input guardrail triggered uid=%s name=%s", uid, g_name)
                error_message = f"InputGuardrailTripwireTriggered: {g_name}"

                if g_name == "guardrail_red_flags_medicos" or "red_flags" in g_name:
                    await _enviar_con_retry(
                        message,
                        "<b>Atención médica recomendada</b>\n\n"
                        "Lo que describes (como dolor de pecho, dificultad respiratoria o mareo grave) es un síntoma de alerta médica inmediata. "
                        "Por tu propia seguridad, <b>detén cualquier actividad física de inmediato</b>, descansa y busca asistencia o valoración médica.\n\n"
                        "Puedes comunicarte a la línea de emergencias local (ej: <b>123</b> en Colombia, <b>911</b> en otros países) si te sientes mal. Tu salud es lo primero.",
                    )
                elif g_name == "guardrail_anti_pollution" or "anti_pollution" in g_name:
                    await _enviar_con_retry(
                        message,
                        "Entiendo que puedas tener dudas o inconvenientes con soporte técnico o facturación de otras plataformas, "
                        "pero mi único rol es ser tu coach deportivo y ayudarte con tus entrenamientos, comidas y descanso saludable.\n\n"
                        "<b>Volvamos a lo nuestro:</b> ¿cómo va tu actividad física hoy? ¿Qué tal estuvo tu entrenamiento o descanso?",
                    )
                else:
                    await _enviar_con_retry(
                        message,
                        "Ese mensaje no se ve bien. Intentalo de nuevo con algo mas claro.",
                    )
                return
            except OutputGuardrailTripwireTriggered:
                logger.warning("Output guardrail (SDK) triggered uid=%s", uid)
                error_message = "OutputGuardrailTripwireTriggered"
                await _enviar_con_retry(
                    message,
                    "Note algo en mi respuesta que prefiero no afirmar. Lo correcto es "
                    "que un profesional medico/nutricionista/psicologo evalue tu caso. "
                    "Sigamos con habitos concretos: que vamos a hacer hoy?",
                )
                await log_evento(uid, "output_guardrail_diagnostico", {"source": "sdk"})
                return
            except openai.BadRequestError as e:
                if "No tool call found" not in str(e):
                    raise
                logger.warning(
                    "Sesion Redis corrupta uid=%s, limpiando y reintentando. "
                    "Error original: %s",
                    uid,
                    str(e)[:200],
                )
                try:
                    await session.close()
                except Exception:
                    logger.debug("Error cerrando session corrupta uid=%s", uid, exc_info=True)
                await limpiar_keys_usuario(uid)
                await log_evento(
                    uid,
                    "sesion_redis_recuperada",
                    {"error": str(e)[:200]},
                )
                session = SafeRedisSession.from_url(
                    str(uid),
                    url=settings.redis_url_str,
                    ttl=settings.session_ttl_seconds,
                )
                result = await Runner.run(
                    coach, prompt, session=session, run_config=RUN_CONFIG
                )
                output = result.final_output

                if result.raw_responses:
                    try:
                        total_in = sum(r.usage.input_tokens for r in result.raw_responses if r.usage)
                        total_out = sum(r.usage.output_tokens for r in result.raw_responses if r.usage)
                        tokens_input = total_in
                        tokens_output = total_out
                        costo_estimado = (total_in / 1_000_000) * 0.15 + (total_out / 1_000_000) * 0.60
                        if settings.coach_model in ("gpt-4o", "gpt-4"):
                            costo_estimado = (total_in / 1_000_000) * 2.50 + (total_out / 1_000_000) * 10.00
                        await log_llm_usage(uid, "coach", settings.coach_model, total_in, total_out, rounds=len(result.raw_responses))
                    except Exception:
                        pass

                diag = detectar_diagnostico_output(output)
                if diag:
                    logger.warning("Output guardrail (regex fallback): diagnostico uid=%s: %s", uid, diag)
                    output = (
                        "Note algo en mi respuesta que prefiero no afirmar. Lo correcto es "
                        "que un profesional medico/nutricionista/psicologo evalue tu caso. "
                        "Sigamos con habitos concretos: que vamos a hacer hoy?"
                    )
                    await log_evento(uid, "output_guardrail_diagnostico", {"matches": diag[:5]})

                respuesta_bot = output
                output_sanitized = _sanitize_telegram_html(output)
                chunks = [output_sanitized[i : i + 4000] for i in range(0, len(output_sanitized), 4000)] or [""]
                for i, chunk in enumerate(chunks):
                    kwargs = {}
                    if with_keyboard and i == len(chunks) - 1:
                        kwargs["reply_markup"] = QUICK_ACTIONS_KEYBOARD
                    await _enviar_con_retry(message, chunk, **kwargs)

                if ctx is not None and ctx.job_queue is not None:
                    await _autocancelar_escalation_si_cumplio(uid, ctx)
        except Exception as e:
            logger.exception("Error procesando mensaje uid=%s", uid)
            error_message = f"{type(e).__name__}: {str(e)}"
            await _enviar_con_retry(
                message,
                "Tuve un saltico tecnico. Vuelve a escribirme y arrancamos.",
            )
        finally:
            await session.close()
    finally:
        # En el finally más externo registramos de forma 100% segura la auditoría de turno
        duracion_ms = int((time.perf_counter() - t_start) * 1000)
        tools_invocadas = current_turn_tools.get()
        try:
            await grabar_auditoria_turno(
                telegram_id=uid,
                request_id=request_id,
                prompt_usuario=prompt_usuario,
                respuesta_bot=respuesta_bot,
                tools_invocadas=tools_invocadas,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                costo_estimado_usd=costo_estimado,
                duracion_ms=duracion_ms,
                error=error_message,
            )
        except Exception as ae:
            logger.warning("Error llamando a grabar_auditoria_turno en finally de _procesar: %s", ae, exc_info=True)

        current_turn_tools.reset(token_tools)
        current_session_uid.reset(token)


async def _autocancelar_escalation_si_cumplio(
    uid: int, ctx: ContextTypes.DEFAULT_TYPE
) -> None:
    """Tras el run del agente, cancela escalation de los tipos cumplidos hoy."""
    try:
        from src.telegram.escalation import _ya_cumplio_hoy, cancelar_escalado_hoy

        user = await obtener_usuario(uid)
        if user is None:
            return
        for tipo in ("entreno", "comida", "sueno", "peso"):
            if await _ya_cumplio_hoy(user.id, tipo):
                await cancelar_escalado_hoy(uid, ctx, tipo)
    except Exception:
        logger.exception("Error cancelando escalation uid=%s", uid)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    nombre = update.effective_user.first_name
    if not await check_rate_limit(uid):
        await update.message.reply_text(
            "Tranquilo, dame un segundo. Estoy procesando lo anterior."
        )
        return
    user = await obtener_o_crear_usuario(uid, nombre)
    await log_evento(uid, "start", {"nombre": nombre})
    await update.message.chat.send_action(ChatAction.TYPING)
    await _procesar(
        update.message,
        "Hola, quiero empezar!",
        uid,
        with_keyboard=user.onboarding_completo,
        ctx=ctx,
    )


async def mensaje(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    texto = update.message.text or ""

    user = await obtener_o_crear_usuario(uid)
    pais = user.pais if user else "CO"
    peso = user.peso_kg if user else None
    crisis = detectar_crisis(texto[:8000], pais=pais, peso_actual_kg=peso)
    if crisis is not None:
        try:
            sent = await update.message.reply_text(crisis.mensaje_contenedor)
            await log_crisis(
                uid,
                nivel=crisis.nivel,
                keywords=crisis.keywords,
                mensaje_usuario=texto[:500],
                mensaje_enviado_id=sent.message_id,
                derivado_a=crisis.lineas_crisis[:120],
            )
            if crisis.nivel == 1:
                await pausar_recordatorios(uid, 7)
                try:
                    from src.telegram.escalation import cancelar_escalado_hoy

                    await cancelar_escalado_hoy(uid, ctx, None)
                except ImportError:
                    pass
                if settings.developer_chat_id:
                    try:
                        await ctx.bot.send_message(
                            chat_id=settings.developer_chat_id,
                            text=(
                                f"<b>CRISIS NIVEL 1</b> uid={uid} pais={pais}\n"
                                f"keywords: {crisis.keywords}\n"
                                f"texto: {texto[:300]}"
                            ),
                        )
                    except Exception:
                        logger.exception("No pude notificar admin de crisis nivel 1")
            await log_evento(uid, "crisis_detected", {"nivel": crisis.nivel})
        except Exception:
            logger.exception("Error manejando crisis uid=%s", uid)
        return

    if len(texto) > settings.max_message_chars:
        await update.message.reply_text(
            f"Mensaje muy largo (limite {settings.max_message_chars} chars). Resume."
        )
        return
    if not await check_rate_limit(uid):
        await update.message.reply_text(
            "Tranquilo, estoy procesando. Espera un momento."
        )
        return
    puede, usado, limite = await check_daily_quota(uid)
    if not puede:
        await update.message.reply_text(
            f"Llegaste a tu limite diario ({limite} mensajes). "
            "Mejora tu plan con /pagar para seguir entrenando."
        )
        return

    # Intercepta etiquetas del reply keyboard persistente. Si el usuario hace
    # tap en "Entrene"/"Comi"/etc., redirigimos al handler o prompt apropiado
    # en vez de mandar el literal al coach (que puede no interpretar bien).
    texto_strip = texto.strip()
    if texto_strip in REPLY_KEYBOARD_INTENTS:
        # Casos especiales que llaman directo a handlers slash para mejor UX:
        if texto_strip == "Tono":
            await cmd_tono(update, ctx)
            return
        if texto_strip == "Agua":
            await cmd_agua(update, ctx)
            return
        if texto_strip == "Calma":
            await cmd_calma(update, ctx)
            return
        if texto_strip == "Mis PRs":
            await cmd_pr(update, ctx)
            return
        # Resto: prompt natural al coach (asi usa las tools correctas).
        prompt = REPLY_KEYBOARD_INTENTS[texto_strip]
        logger.info(
            "reply_keyboard intent uid=%s label=%r -> prompt=%r",
            uid, texto_strip, prompt,
        )
        await update.message.chat.send_action(ChatAction.TYPING)
        await _procesar(update.message, prompt, uid, ctx=ctx)
        return

    await reaccionar(update.message, ctx)

    if _CONFIRMACION_ENTRENO.search(texto):
        try:
            from src.telegram.escalation import cancelar_escalado_hoy

            await cancelar_escalado_hoy(uid, ctx, "entreno")
        except ImportError:
            pass

    await update.message.chat.send_action(ChatAction.TYPING)
    await _procesar(update.message, texto, uid, ctx=ctx)


async def menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Menu principal: inline keyboard 6 categorias + reply persistente."""
    keyboard = [
        # Registro del dia (lo mas frecuente)
        [
            InlineKeyboardButton("Entreno", callback_data="entreno"),
            InlineKeyboardButton("Comida", callback_data="comida"),
            InlineKeyboardButton("Sueno", callback_data="sueno"),
        ],
        [
            InlineKeyboardButton("Peso", callback_data="peso"),
            InlineKeyboardButton("Agua", callback_data="menu_agua"),
            InlineKeyboardButton("Calma", callback_data="menu_calma"),
        ],
        # Resumenes / progreso
        [
            InlineKeyboardButton("Plan de hoy", callback_data="plan_hoy"),
            InlineKeyboardButton("Reporte semanal", callback_data="reporte"),
        ],
        [
            InlineKeyboardButton("Mi mes (PDF)", callback_data="menu_mi_mes"),
            InlineKeyboardButton("Grafico progreso", callback_data="menu_grafico"),
        ],
        [
            InlineKeyboardButton("Mis PRs", callback_data="menu_pr"),
            InlineKeyboardButton("Historial peso", callback_data="historial_peso"),
        ],
        # Compromiso / coach
        [
            InlineKeyboardButton("Mi compromiso", callback_data="compromiso"),
            InlineKeyboardButton("Recordatorios", callback_data="menu_recordatorios"),
        ],
        [
            InlineKeyboardButton("Cambiar tono", callback_data="cambiar_tono"),
            InlineKeyboardButton("Configuracion", callback_data="menu_config"),
        ],
        # Comunidad / Pro
        [
            InlineKeyboardButton("Desafios", callback_data="menu_desafios"),
            InlineKeyboardButton("Ranking", callback_data="menu_ranking"),
            InlineKeyboardButton("Invitar", callback_data="menu_invitar"),
        ],
        [
            InlineKeyboardButton("Mejorar plan", callback_data="menu_pagar"),
            InlineKeyboardButton("Ayuda", callback_data="menu_ayuda"),
        ],
    ]
    await update.message.reply_text(
        "<b>Que quieres hacer?</b>\n\n"
        "Toca cualquier boton, o usa los del teclado de abajo.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    await update.message.reply_text(
        "Tip: los botones de abajo estan siempre disponibles.",
        reply_markup=QUICK_ACTIONS_KEYBOARD,
    )


async def reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Limpia la sesion de Redis del usuario para resolver historial corrupto."""
    uid = update.effective_user.id
    try:
        n = await limpiar_keys_usuario(uid)
        await log_evento(uid, "reset", {"keys_borradas": n})
        await update.message.reply_text(
            "Listo! Tu sesion fue reiniciada. Escribe /start para comenzar de nuevo."
        )
    except Exception:
        logger.exception("Error reseteando sesion uid=%s", uid)
        await update.message.reply_text(
            "No pude reiniciar la sesion. Intenta de nuevo en un momento."
        )


async def borrar_datos(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    username = update.effective_user.username
    logger.info(
        "borrar_datos solicitado uid=%s username=%s",
        uid,
        username,
    )
    keyboard = [
        [
            InlineKeyboardButton(
                "Si, borrar TODOS mis datos", callback_data="confirmar_borrado"
            )
        ]
    ]
    await update.message.reply_text(
        "Esto eliminara permanentemente TODOS tus datos:\n"
        "- Perfil y onboarding\n"
        "- Entrenamientos y PRs\n"
        "- Comidas y nutricion\n"
        "- Sueno y metricas corporales\n"
        "- Historial conversacional\n\n"
        "Esta accion NO se puede deshacer. Estas seguro?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cmd_pausa(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Pausa recordatorios N dias (default 1)."""
    uid = update.effective_user.id
    args = ctx.args or []
    try:
        dias = max(1, min(30, int(args[0]))) if args else 1
    except (ValueError, IndexError):
        dias = 1
    await pausar_recordatorios(uid, dias)
    await log_evento(uid, "pausa", {"dias": dias})
    await update.message.reply_text(
        f"Pausa de <b>{dias} dia(s)</b>. No te molesto. Cuando estes listo, escribeme."
    )


async def cmd_porque_me_escribiste(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Transparencia algoritmica: muestra los ultimos 3 eventos del bot."""
    uid = update.effective_user.id
    eventos = await ultimos_eventos(uid, limit=3)
    if not eventos:
        await update.message.reply_text(
            "No tengo registros recientes que mostrarte."
        )
        return
    lineas = ["<b>Por que te escribi recientemente:</b>"]
    for e in eventos:
        cuando = e.creado_en.strftime("%Y-%m-%d %H:%M") if e.creado_en else "?"
        lineas.append(f"- <code>{cuando}</code> {e.tipo_evento}")
    lineas.append("\nSi alguno te incomoda, usa /tono o /pausa.")
    await update.message.reply_text("\n".join(lineas))


async def cmd_tono(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline keyboard con los 3 tonos."""
    keyboard = [
        [
            InlineKeyboardButton("Amigable", callback_data="tono:amigable"),
            InlineKeyboardButton("Firme", callback_data="tono:firme"),
            InlineKeyboardButton("Militar", callback_data="tono:militar"),
        ]
    ]
    user = await obtener_usuario(update.effective_user.id)
    actual = user.tono.value if user and user.tono else "firme"
    await update.message.reply_text(
        f"Tu tono actual: <b>{actual}</b>.\n\n"
        "Elige nuevo tono:\n"
        "- <b>Amigable</b>: empatico, suave.\n"
        "- <b>Firme</b>: directo, te recuerda los compromisos.\n"
        "- <b>Militar</b>: imperativo, escala fuerte cuando fallas.\n",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# Atajos slash que reusan el agente: el usuario los ve en el menu como botones
# y los puede tipear directo como comando. Cada uno reusa _procesar con un
# prompt traducido para que el coach reaccione igual que con el callback.
_MENU_SLASH_PROMPTS = {
    "entreno": "Quiero registrar mi entrenamiento de hoy",
    "comida": "Quiero registrar lo que comi hoy",
    "sueno": "Quiero registrar como dormi anoche",
    "historial_peso": "Muestrame mi historial de peso",
}


def _make_menu_slash_handler(prompt: str):
    """Factory: crea un handler que dispara _procesar con un prompt fijo."""

    async def _handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        uid = update.effective_user.id
        if not await check_rate_limit(uid):
            await update.message.reply_text("Tranquilo, dame un segundo.")
            return
        await update.message.chat.send_action(ChatAction.TYPING)
        await _procesar(update.message, prompt, uid, ctx=ctx)

    return _handler


async def cmd_quiet_hours(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Cambia quiet hours. Uso: /quiet_hours 22:00 07:00"""
    uid = update.effective_user.id
    args = ctx.args or []
    if len(args) != 2:
        await update.message.reply_text(
            "Uso: <code>/quiet_hours HH:MM HH:MM</code>\n"
            "Ej: <code>/quiet_hours 22:00 07:00</code>"
        )
        return
    try:
        inicio, fin = args[0], args[1]
        await set_quiet_hours(uid, inicio, fin)
        await log_evento(uid, "quiet_hours", {"inicio": inicio, "fin": fin})
        await update.message.reply_text(
            f"Listo. No te molesto entre <b>{inicio}</b> y <b>{fin}</b>."
        )
    except Exception:
        await update.message.reply_text(
            "Formato invalido. Usa HH:MM 24h: <code>/quiet_hours 22:00 07:00</code>"
        )


async def cmd_apagar_firme(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Baja el tono a amigable y reduce intensidad."""
    uid = update.effective_user.id
    await repo_cambiar_tono(uid, "amigable")
    await log_evento(uid, "apagar_firme", {})
    await update.message.reply_text(
        "Tono cambiado a <b>amigable</b>. Voy a bajar la intensidad de los "
        "recordatorios. Si necesitas pausa total, usa /pausa N."
    )


async def cmd_salir(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Offboarding etico: tono amigable + pausa larga + opcion borrar datos."""
    uid = update.effective_user.id
    await repo_cambiar_tono(uid, "amigable")
    await pausar_recordatorios(uid, 30)
    await log_evento(uid, "salir", {})
    keyboard = [
        [
            InlineKeyboardButton(
                "Si, borrar todo", callback_data="confirmar_borrado"
            )
        ]
    ]
    await update.message.reply_text(
        "Listo. Pause los recordatorios <b>30 dias</b> y baje el tono a amigable.\n\n"
        "Cuando quieras retomar, escribime y volvemos a la rutina.\n\n"
        "Si prefieres borrar todos tus datos, pulsa abajo:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cmd_dia_libre(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Consume 1 freeze para no romper el streak hoy."""
    uid = update.effective_user.id
    ok = await usar_freeze_streak(uid, "entreno")
    if ok:
        await log_evento(uid, "dia_libre", {"ok": True})
        await update.message.reply_text(
            "Listo, dia libre usado. No rompe tu streak. Manana volvemos."
        )
    else:
        await update.message.reply_text(
            "No tienes <i>freezes</i> disponibles. Se regenera 1 cada 30 dias."
        )


async def cmd_feedback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Pide rating 1-5 con ForceReply."""
    await update.message.reply_text(
        "Como te estoy tratando? Responde con un numero del <b>1 al 5</b>.",
        reply_markup=ForceReply(selective=True, input_field_placeholder="1-5"),
    )


async def cmd_codigo_web(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Genera codigo de 6 digitos para login web en https://entrenadorax.axsoftware.codes/login.

    El codigo expira en 15 minutos y es single-use. Solo un codigo activo
    por usuario; pedir uno nuevo invalida el anterior.
    """
    from src.services.codigo_web import CODIGO_TTL_SECONDS, generar_codigo

    uid = update.effective_user.id
    try:
        codigo = await generar_codigo(uid)
    except Exception:
        logger.exception("Error generando codigo_web uid=%s", uid)
        await update.message.reply_text(
            "Tuve un problema generando el codigo. Intenta de nuevo en un momento."
        )
        return
    minutos = CODIGO_TTL_SECONDS // 60
    landing_url = (
        str(settings.landing_url).rstrip("/") if settings.landing_url
        else "https://entrenadorax.axsoftware.codes"
    )
    await update.message.reply_text(
        f"<b>Tu codigo de acceso web</b>\n\n"
        f"<code>{codigo}</code>\n\n"
        f"1) Abre <a href=\"{landing_url}/login\">{landing_url}/login</a>\n"
        f"2) Tab 'Deportista' -> pega el codigo\n"
        f"3) Listo, entras a tu panel.\n\n"
        f"El codigo vence en {minutos} minutos y solo sirve una vez. "
        f"Si te lo pierdes, manda /codigo_web otra vez.",
        disable_web_page_preview=True,
    )
    logger.info("cmd_codigo_web enviado uid=%s", uid)


async def cmd_presumir(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Compartir ultimo PR a un grupo del usuario."""
    keyboard = [
        [
            KeyboardButton(
                "Elegir chat para compartir",
                request_chat=KeyboardButtonRequestChat(
                    request_id=1,
                    chat_is_channel=False,
                ),
            )
        ]
    ]
    await update.message.reply_text(
        "Elige el chat donde quieres presumir tu PR:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard, resize_keyboard=True, one_time_keyboard=True
        ),
    )


async def cmd_hoy(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Delega al agente: que toca hoy."""
    uid = update.effective_user.id
    if not await check_rate_limit(uid):
        await update.message.reply_text("Tranquilo, dame un segundo.")
        return
    await update.message.chat.send_action(ChatAction.TYPING)
    await _procesar(update.message, "Que toca hoy en mi plan?", uid)


async def cmd_pr(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Delega al agente: lista mis PRs."""
    uid = update.effective_user.id
    if not await check_rate_limit(uid):
        await update.message.reply_text("Tranquilo, dame un segundo.")
        return
    await update.message.chat.send_action(ChatAction.TYPING)
    await _procesar(update.message, "Lista todos mis PRs", uid)


async def cmd_reporte(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Delega al agente: reporte semanal."""
    uid = update.effective_user.id
    if not await check_rate_limit(uid):
        await update.message.reply_text("Tranquilo, dame un segundo.")
        return
    await update.message.chat.send_action(ChatAction.TYPING)
    await _procesar(update.message, "Dame mi reporte semanal completo", uid)


async def cmd_compromiso(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Delega al agente: ver o firmar compromiso."""
    uid = update.effective_user.id
    if not await check_rate_limit(uid):
        await update.message.reply_text("Tranquilo, dame un segundo.")
        return
    await update.message.chat.send_action(ChatAction.TYPING)
    user = await obtener_usuario(uid)
    compromiso = await obtener_compromiso_activo(uid) if user else None
    if compromiso:
        await _procesar(update.message, "Muestrame mi compromiso actual", uid)
    else:
        await _procesar(
            update.message, "Quiero firmar un nuevo compromiso conmigo mismo", uid
        )


async def cmd_firmar_compromiso(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Atajo al flow de firma."""
    uid = update.effective_user.id
    await update.message.chat.send_action(ChatAction.TYPING)
    await _procesar(
        update.message, "Quiero firmar un compromiso conmigo mismo", uid
    )


async def cmd_peso(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not await check_rate_limit(uid):
        await update.message.reply_text("Tranquilo, dame un segundo.")
        return
    await update.message.chat.send_action(ChatAction.TYPING)
    await _procesar(update.message, "Quiero registrar mi peso actual", uid)


async def cmd_upgrade(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia invoice para activar EntrenadorAX Pro (100 Stars/mes ~ USD 1.99)."""
    uid = update.effective_user.id
    try:
        await ctx.bot.send_invoice(
            chat_id=uid,
            title="EntrenadorAX Pro",
            description=(
                "1 mes de Pro:\n"
                "- Voz del coach en mensajes intensos\n"
                "- Photo meal feedback ilimitado\n"
                "- Charts avanzados y export CSV ilimitado\n"
                "- Recordatorios prioritarios\n"
                "- Sin cap de plan generator"
            ),
            payload=f"pro_mensual_{uid}_{int(datetime.utcnow().timestamp())}",
            currency="XTR",
            prices=[LabeledPrice("EntrenadorAX Pro Mensual", 100)],
            start_parameter="upgrade_pro",
        )
        await log_evento(uid, "upgrade_invoice_enviado", {})
    except Exception:
        logger.exception("Error enviando invoice uid=%s", uid)
        await update.message.reply_text("No pude crear el pago ahora. Reintenta en un momento.")


async def precheckout_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Aprueba el pre-checkout en <10s con validacion de payload, monto y dup."""
    from src.db.repository import es_usuario_pro

    q = update.pre_checkout_query
    uid = q.from_user.id
    try:
        if not q.invoice_payload.startswith(f"pro_mensual_{uid}_"):
            await q.answer(
                ok=False, error_message="Payload invalido. Reinicia con /upgrade."
            )
            return
        if q.total_amount != 100:
            await q.answer(ok=False, error_message="Monto invalido.")
            return
        if await es_usuario_pro(uid):
            await q.answer(ok=False, error_message="Ya tienes Pro activo.")
            return
        await q.answer(ok=True)
    except Exception:
        logger.exception("Error precheckout uid=%s", uid)
        try:
            await q.answer(ok=False, error_message="Error temporal. Intenta de nuevo.")
        except Exception:
            pass


async def successful_payment_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Activa Pro al recibir successful_payment. Idempotente vs duplicados."""
    from sqlalchemy.exc import IntegrityError

    from src.db.repository import activar_suscripcion_pro

    uid = update.effective_user.id
    payment = update.message.successful_payment
    try:
        await activar_suscripcion_pro(
            uid,
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
            star_amount=payment.total_amount,
            dias=30,
        )
    except IntegrityError:
        logger.info(
            "Pago duplicado uid=%s charge_id=%s (ya activado)",
            uid,
            payment.telegram_payment_charge_id,
        )
    except Exception:
        logger.exception("Error activando Pro uid=%s", uid)
        await update.message.reply_text(
            "Recibi el pago pero hubo problema activando. Contacta soporte."
        )
        return
    await log_evento(
        uid,
        "pro_activado",
        {
            "stars": payment.total_amount,
            "charge_id": payment.telegram_payment_charge_id,
        },
    )
    await update.message.reply_text(
        "<b>EntrenadorAX Pro activado!</b> Gracias por confiar. "
        "Vas a notar voz en mensajes intensos, photos ilimitadas y charts top. "
        "Cualquier cosa, /ayuda."
    )


async def cmd_invitar(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Genera link de invitacion con tracking."""
    uid = update.effective_user.id
    me = await ctx.bot.get_me()
    bot_username = me.username
    link = f"https://t.me/{bot_username}?start=ref_{uid}"
    await log_evento(uid, "invitar_generado", {})
    await update.message.reply_text(
        "<b>Invita amigos a EntrenadorAX</b>\n\n"
        f"Comparte este link: <code>{link}</code>\n\n"
        "Cuando se queden 30 dias, recibis 1 mes de Pro gratis."
    )


async def inline_query(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """@bot mi reporte -> articulo compartible."""
    from telegram import (
        InlineQueryResultArticle,
        InputTextMessageContent,
    )

    q = update.inline_query
    if not q:
        return
    uid = q.from_user.id
    query = (q.query or "").lower().strip()

    results = []
    try:
        if "reporte" in query or "semana" in query or not query:
            from src.db.repository import reporte_semanal

            r = await reporte_semanal(uid)
            texto = (
                f"<b>Mi semana en EntrenadorAX:</b>\n"
                f"Dias entrenados: <b>{r.get('dias_entrenados', 0)}</b>\n"
                f"Volumen: <b>{r.get('volumen_total_kg', 0):.0f} kg</b>\n"
                f"Nuevos PRs: <b>{len(r.get('nuevos_prs', []))}</b>"
            )
            results.append(
                InlineQueryResultArticle(
                    id="reporte_semanal",
                    title="Compartir mi reporte semanal",
                    description=f"{r.get('dias_entrenados', 0)} dias entrenados",
                    input_message_content=InputTextMessageContent(
                        message_text=texto, parse_mode="HTML"
                    ),
                )
            )
        if "pr" in query:
            from src.db.repository import listar_prs

            prs = await listar_prs(uid)
            if prs:
                top = max(prs, key=lambda p: p.peso_kg or 0)
                texto = (
                    f"<b>Mi PR:</b> {top.ejercicio} "
                    f"<b>{top.peso_kg} kg</b> x{top.reps} reps. "
                    f"Tracking con EntrenadorAX."
                )
                results.append(
                    InlineQueryResultArticle(
                        id="top_pr",
                        title=f"Top PR: {top.ejercicio} {top.peso_kg}kg",
                        description="Compartir tu mejor PR",
                        input_message_content=InputTextMessageContent(
                            message_text=texto, parse_mode="HTML"
                        ),
                    )
                )
    except Exception:
        logger.exception("Error inline_query uid=%s", uid)

    try:
        await q.answer(results=results, cache_time=60, is_personal=True)
    except Exception:
        logger.exception("Error answer inline uid=%s", uid)


@requiere_tier(PlanSuscripcion.STARTER)
async def cmd_grafico(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia un chart segun el tipo. Uso: /grafico [peso|volumen|macros|streak|resumen]"""
    from src.services.charts import (
        chart_macros_dia,
        chart_peso,
        chart_reporte_semanal,
        chart_streak_calendario,
        chart_volumen_semanal,
    )

    uid = update.effective_user.id
    args = ctx.args or []
    tipo = args[0].lower().strip() if args else "resumen"
    await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
    fn = {
        "peso": chart_peso,
        "volumen": chart_volumen_semanal,
        "macros": chart_macros_dia,
        "streak": chart_streak_calendario,
        "resumen": chart_reporte_semanal,
    }.get(tipo, chart_reporte_semanal)
    try:
        img = await fn(uid)
        if img is None:
            await update.message.reply_text(
                "No tengo suficientes datos para este grafico. Registra mas y vuelve."
            )
            return
        await ctx.bot.send_photo(
            chat_id=uid, photo=img, caption=f"<b>Tu chart {tipo}</b>"
        )
    except Exception:
        logger.exception("Error generando grafico %s uid=%s", tipo, uid)
        await update.message.reply_text("No pude generar el grafico ahora.")


async def cmd_exportar_csv(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Exporta entrenos de los ultimos 30 dias (Pro: ilimitado)."""
    from datetime import date, timedelta
    from io import BytesIO

    from src.db.repository import es_usuario_pro, obtener_ultimas_sesiones

    uid = update.effective_user.id
    es_pro = await es_usuario_pro(uid)
    limite = 365 if es_pro else 30
    try:
        sesiones = await obtener_ultimas_sesiones(uid, limite=500)
        if not sesiones:
            await update.message.reply_text("Aun no tienes sesiones registradas.")
            return
        corte = date.today() - timedelta(days=limite)
        sesiones = [s for s in sesiones if s.fecha >= corte]
        lines = ["fecha,tipo,duracion_min,ejercicio,series,reps,peso_kg,rpe"]
        for s in sesiones:
            tipo = s.tipo.value if s.tipo else ""
            for ej in s.ejercicios:
                lines.append(
                    f"{s.fecha},{tipo},{s.duracion_min or ''},{ej.nombre or ''},"
                    f"{ej.series or ''},{ej.reps or ''},{ej.peso_kg or ''},{ej.rpe or ''}"
                )
        csv_bytes = ("\n".join(lines)).encode("utf-8")
        await ctx.bot.send_document(
            chat_id=uid,
            document=BytesIO(csv_bytes),
            filename=f"entrenos_{date.today().isoformat()}.csv",
            caption=(
                f"<b>{len(sesiones)} sesiones</b> exportadas "
                f"({'Pro - ilimitado' if es_pro else f'free - {limite} dias'})."
            ),
        )
        await log_evento(uid, "exportar_csv", {"n_sesiones": len(sesiones)})
    except Exception:
        logger.exception("Error exportando CSV uid=%s", uid)
        await update.message.reply_text("No pude exportar el CSV. Intenta de nuevo.")


async def cmd_ayuda(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "<b>Como funciono</b>\n\n"
        "1) Escribeme cualquier cosa: 'hice pierna hoy 4x8 sentadilla 80kg', "
        "'almorce pollo y arroz', 'dormi 7h', 'peso 82kg'.\n"
        "2) Mandame foto del plato y te calculo macros (tambien etiquetas).\n"
        "3) Acepto notas de voz: las transcribo y las proceso.\n"
        "4) Pideme recordatorios: 'despiertame a las 7am', 'avisame en 30 min'.\n"
        "5) Yo te recuerdo entrenar, comer y dormir si no lo haces.\n"
        "6) Si fallaste, te corrijo. Si me corriges, edito (no inventes).\n\n"
        "<b>Registro del dia</b>\n"
        "   /menu - menu principal con botones\n"
        "   /hoy - plan + resumen de hoy\n"
        "   /entreno - registrar entrenamiento\n"
        "   /comida - registrar comida\n"
        "   /sueno - registrar sueno\n"
        "   /peso - registrar peso\n"
        "   /agua - registrar agua / ver hidratacion\n"
        "   /calma - 3 minutos de respiracion guiada\n\n"
        "<b>Progreso y reportes</b>\n"
        "   /reporte - resumen semanal completo\n"
        "   /pr - mis Personal Records\n"
        "   /grafico - grafico visual de progreso\n"
        "   /mi_mes - analisis mensual en PDF\n"
        "   /historial_peso - histograma de peso\n"
        "   /compromiso - ver/firmar mi pacto\n"
        "   /firmar_compromiso - firmar nuevo compromiso\n\n"
        "<b>Configuracion del coach</b>\n"
        "   /tono - amigable, firme o militar\n"
        "   /quiet_hours HH:MM HH:MM - no molestar\n"
        "   /pausa N - silenciarme N dias\n"
        "   /dia_libre - usar freeze (no rompe streak)\n"
        "   /apagar_firme - bajar a modo amigable\n"
        "   /salir - bajar tono y reducir mensajes\n\n"
        "<b>Pro / comunidad</b>\n"
        "   /pagar - comprar plan (Bre-B, Nequi, etc.)\n"
        "   /planes - ver opciones de plan\n"
        "   /upgrade - activar via Telegram Stars\n"
        "   /llamar - llamada de voz con el coach\n"
        "   /codigo_web - codigo para entrar al panel web\n"
        "   /desafios - desafios de la comunidad\n"
        "   /ranking - top de la semana\n"
        "   /kudos - dar/recibir kudos\n"
        "   /invitar - invitar amigo\n"
        "   /presumir - compartir un logro\n\n"
        "<b>Cuenta y datos</b>\n"
        "   /exportar_csv - bajar mis datos\n"
        "   /feedback - mandar feedback al equipo\n"
        "   /porque_me_escribiste - explico por que te escribi\n"
        "   /reset - reiniciar onboarding\n"
        "   /borrar_datos - eliminar TODO\n\n"
        "<b>Privacidad:</b> tus datos son tuyos. Puedes borrar todo "
        "cuando quieras con /borrar_datos. Tambien puedes exportarlos a "
        "CSV con /exportar_csv."
    )


async def boton(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    # Admin: aprobar/rechazar comprobante desde Telegram (solo developer_chat_id)
    if q.data.startswith("admin_aprobar:") or q.data.startswith("admin_rechazar:"):
        if str(uid) != str(settings.developer_chat_id):
            await q.answer("No tienes permiso para esta accion.", show_alert=True)
            return
        accion, comp_id_str = q.data.split(":", 1)
        try:
            comp_id = int(comp_id_str)
        except ValueError:
            return
        from src.db.repository import aprobar_comprobante, rechazar_comprobante
        from src.services.pricing import formatear_precio
        try:
            if accion == "admin_aprobar":
                comp = await aprobar_comprobante(comp_id, "admin@telegram", "")
                if comp is None:
                    await q.edit_message_caption(
                        caption=q.message.caption + "\n\nYa fue procesado anteriormente.",
                    )
                    return
                # Activar plan del usuario
                from src.db.models import MetodoPago
                from sqlalchemy import select
                from src.db.connection import async_session_factory
                from src.db.models import Usuario
                async with async_session_factory() as session:
                    result = await session.execute(
                        select(Usuario.telegram_id).where(Usuario.id == comp.usuario_id)
                    )
                    uid_telegram = result.scalar_one()
                await activar_plan(
                    telegram_id=uid_telegram,
                    plan=comp.plan_solicitado,
                    dias=comp.dias_otorgados,
                    metodo=comp.metodo or MetodoPago.OTRO,
                    monto_cop=comp.monto_cop,
                    comprobante_id=comp.id,
                )
                # Notificar al usuario
                try:
                    await ctx.bot.send_message(
                        chat_id=uid_telegram,
                        text=(
                            f"<b>Pago aprobado!</b> Tu plan <b>{comp.plan_solicitado.value}</b> "
                            f"esta activo. Gracias por confiar en EntrenadorAX!"
                        ),
                    )
                except Exception:
                    pass
                # Actualizar el caption de la notificacion
                await q.edit_message_caption(
                    caption=q.message.caption + "\n\nAPROBADO. Plan activado.",
                )
                logger.info("admin_aprobar comp_id=%s por uid=%s", comp_id, uid)
            else:
                comp = await rechazar_comprobante(comp_id, "admin@telegram", "Rechazado via Telegram")
                if comp is None:
                    await q.edit_message_caption(
                        caption=q.message.caption + "\n\nYa fue procesado anteriormente.",
                    )
                    return
                # Notificar al usuario
                from sqlalchemy import select
                from src.db.connection import async_session_factory
                from src.db.models import Usuario
                async with async_session_factory() as session:
                    result = await session.execute(
                        select(Usuario.telegram_id).where(Usuario.id == comp.usuario_id)
                    )
                    uid_telegram = result.scalar_one()
                try:
                    await ctx.bot.send_message(
                        chat_id=uid_telegram,
                        text=(
                            "Tu comprobante fue revisado y <b>no se pudo validar</b>. "
                            "Si crees que es un error, contacta soporte por WhatsApp: "
                            "https://wa.me/573044093197"
                        ),
                    )
                except Exception:
                    pass
                await q.edit_message_caption(
                    caption=q.message.caption + "\n\nRECHAZADO.",
                )
                logger.info("admin_rechazar comp_id=%s por uid=%s", comp_id, uid)
        except Exception:
            logger.exception("Error en admin_%s comp_id=%s", accion, comp_id_str)
            await q.edit_message_caption(
                caption=q.message.caption + "\n\nError procesando. Revisa en el panel web.",
            )
        return

    if q.data.startswith("tono:"):
        nuevo = q.data.split(":", 1)[1]
        if nuevo == "militar":
            user = await obtener_usuario(uid)
            if user is None or user.modo_militar_aceptado_en is None:
                keyboard = [
                    [
                        InlineKeyboardButton(
                            "Acepto el modo militar",
                            callback_data="aceptar_militar",
                        )
                    ]
                ]
                await q.edit_message_text(
                    "<b>Modo militar - disclaimer</b>\n\n"
                    "Te enviare mensajes mas intensos escalando frecuencia y "
                    "dureza si fallas tu compromiso. NUNCA cruzaremos a "
                    "humillaciones, ataques al cuerpo o lenguaje toxico. Maximo "
                    "2 mensajes/dia y cada 30 dias te pregunto si quieres "
                    "seguir.\n\n"
                    "<b>NO recomiendo</b> modo militar si tienes o tuviste: "
                    "ansiedad, depresion, trastorno alimenticio, TOC, PTSD, "
                    "dismorfia corporal, RED-S, embarazo, postparto reciente, "
                    "o eres menor de 18. Si estas en tratamiento, consultalo "
                    "con tu profesional antes.\n\n"
                    "Aceptas?",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return
        await repo_cambiar_tono(uid, nuevo)
        await log_evento(uid, "cambio_tono", {"tono": nuevo})
        await q.edit_message_text(f"Tono cambiado a <b>{nuevo}</b>.")
        return

    if q.data == "aceptar_militar":
        await aceptar_modo_militar(uid)
        await repo_cambiar_tono(uid, "militar")
        await log_evento(uid, "acepto_militar", {})
        await q.edit_message_text(
            "Aceptado. Modo militar activado. <b>Sin excusas.</b>"
        )
        return

    if q.data.startswith("agua:"):
        from src.services.hidratacion import (
            consumo_hoy_ml,
            objetivo_ml,
            registrar_agua,
        )

        try:
            ml = int(q.data.split(":", 1)[1])
        except ValueError:
            return
        await registrar_agua(uid, ml)
        await log_evento(uid, "agua_registrada", {"ml": ml})
        consumido = await consumo_hoy_ml(uid)
        objetivo = await objetivo_ml(uid)
        pct = int(consumido / objetivo * 100) if objetivo else 0
        keyboard = [
            [
                InlineKeyboardButton("+250ml", callback_data="agua:250"),
                InlineKeyboardButton("+500ml", callback_data="agua:500"),
                InlineKeyboardButton("+750ml", callback_data="agua:750"),
            ]
        ]
        await q.edit_message_text(
            f"<b>Hidratacion hoy</b>\n{consumido}ml / {objetivo}ml ({pct}%)",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if q.data.startswith("calma:"):
        from io import BytesIO

        from src.services.mindfulness import obtener_audio, SESIONES

        slug = q.data.split(":", 1)[1]
        sesion = SESIONES.get(slug)
        if sesion is None:
            return
        await q.message.chat.send_action(ChatAction.RECORD_VOICE)
        audio = await obtener_audio(slug)
        if audio is None:
            await q.edit_message_text("No pude generar el audio ahora.")
            return
        try:
            await ctx.bot.send_voice(
                chat_id=uid,
                voice=BytesIO(audio),
                caption=f"<b>{sesion['titulo']}</b>",
            )
            await q.delete_message()
        except Exception:
            logger.exception("Error enviando mindfulness uid=%s", uid)
        return

    if q.data.startswith("desafio_inscribir:"):
        from src.services.comunidad import inscribir_en_desafio

        slug = q.data.split(":", 1)[1]
        ok = await inscribir_en_desafio(uid, slug)
        if ok:
            await q.edit_message_text(
                f"Inscripto en <b>{slug}</b>. Usa /ranking para ver tu posicion."
            )
        else:
            await q.edit_message_text(
                "Ya estabas inscrito o el desafio no existe."
            )
        return

    if q.data.startswith("pagar:"):
        from src.db.models import DuracionPago, PlanSuscripcion
        from src.services.pricing import (
            descripcion_plan,
            dias_duracion,
            formatear_precio,
            precio_cop,
        )

        partes = q.data.split(":")
        if len(partes) >= 3:
            plan_str, duracion_str = partes[1], partes[2]
        else:
            plan_str, duracion_str = partes[1], "mensual"
        try:
            plan_pago = PlanSuscripcion(plan_str)
            duracion = DuracionPago(duracion_str)
        except ValueError:
            await q.edit_message_text("Opcion invalida.")
            return
        monto = precio_cop(plan_pago, duracion)
        dias = dias_duracion(plan_pago, duracion)
        ctx.user_data["esperando_comprobante"] = True
        ctx.user_data["plan_pendiente_pago"] = {
            "plan": plan_pago.value,
            "duracion": duracion.value,
            "monto": monto,
            "dias": dias,
        }
        await log_evento(
            uid,
            "pagar_seleccionado",
            {"plan": plan_pago.value, "duracion": duracion.value, "monto": monto},
        )
        await q.edit_message_text(
            f"<b>Plan {plan_pago.value} ({duracion.value}): {formatear_precio(monto)}</b>\n\n"
            f"{descripcion_plan(plan_pago)}\n\n"
            f"<b>Como pagar:</b>\n"
            f"Transfiere a esta llave Nu:\n"
            f"<code>{settings.cuenta_destino_pago}</code>\n\n"
            f"Aceptamos transferencias de cualquier banco o billetera "
            f"(Nequi, Daviplata, Bancolombia, Bre-B, etc.).\n\n"
            f"Cuando termines, mandame la <b>foto del comprobante</b>. "
            f"La activacion es automatica si el monto coincide; "
            f"un admin la valida en maximo 24h."
        )
        return

    if q.data == "confirmar_borrado":
        logger.info("borrar_datos confirmado uid=%s", uid)
        borrado = False
        keys_redis = 0
        evento_ok = False
        fallo_critico = False
        try:
            borrado = await eliminar_usuario(uid)
            logger.info(
                "borrar_datos DB delete uid=%s borrado=%s", uid, borrado
            )
        except Exception:
            fallo_critico = True
            logger.exception(
                "borrar_datos fallo en eliminar_usuario uid=%s", uid
            )
        if not fallo_critico:
            try:
                keys_redis = await limpiar_keys_usuario(uid)
                logger.info(
                    "borrar_datos Redis cleanup uid=%s keys=%d",
                    uid,
                    keys_redis,
                )
            except Exception:
                logger.exception(
                    "borrar_datos fallo en limpiar_keys uid=%s "
                    "(DB ya estaba borrada)",
                    uid,
                )
            try:
                await log_evento(uid, "borrar_datos", {"existia": borrado})
                evento_ok = True
            except Exception:
                logger.exception(
                    "borrar_datos fallo en log_evento uid=%s "
                    "(no critico)",
                    uid,
                )
        logger.info(
            "audit.borrar_datos uid=%s ok=%s db_borrado=%s "
            "redis_keys=%d evento_ok=%s",
            uid,
            not fallo_critico,
            borrado,
            keys_redis,
            evento_ok,
        )
        if fallo_critico:
            await q.edit_message_text(
                "Hubo un error eliminando tus datos. "
                "Intenta de nuevo en un momento."
            )
            return
        if borrado:
            await q.edit_message_text(
                "Todos tus datos han sido eliminados permanentemente. "
                "Usa /start para comenzar desde cero."
            )
        else:
            await q.edit_message_text(
                "No encontre datos asociados a tu cuenta. "
                "Usa /start para empezar."
            )
        return

    # Callbacks "menu_X" que redirigen a comandos slash existentes.
    # Asi reutilizamos sus handlers sin duplicar logica.
    if q.data == "menu_agua":
        await cmd_agua(_FakeUpdate(q.message, q.from_user), ctx)
        return
    if q.data == "menu_calma":
        await cmd_calma(_FakeUpdate(q.message, q.from_user), ctx)
        return
    if q.data == "menu_mi_mes":
        await cmd_mi_mes(_FakeUpdate(q.message, q.from_user), ctx)
        return
    if q.data == "menu_grafico":
        await cmd_grafico(_FakeUpdate(q.message, q.from_user), ctx)
        return
    if q.data == "menu_pr":
        await cmd_pr(_FakeUpdate(q.message, q.from_user), ctx)
        return
    if q.data == "menu_desafios":
        await cmd_desafios(_FakeUpdate(q.message, q.from_user), ctx)
        return
    if q.data == "menu_ranking":
        await cmd_ranking(_FakeUpdate(q.message, q.from_user), ctx)
        return
    if q.data == "menu_invitar":
        await cmd_invitar(_FakeUpdate(q.message, q.from_user), ctx)
        return
    if q.data == "menu_pagar":
        await cmd_pagar(_FakeUpdate(q.message, q.from_user), ctx)
        return
    if q.data == "menu_ayuda":
        await cmd_ayuda(_FakeUpdate(q.message, q.from_user), ctx)
        return
    if q.data == "menu_config":
        kb = [
            [
                InlineKeyboardButton("Cambiar tono", callback_data="cambiar_tono"),
                InlineKeyboardButton("No molestar", callback_data="menu_quiet"),
            ],
            [
                InlineKeyboardButton("Pausar bot", callback_data="menu_pausa"),
                InlineKeyboardButton("Dia libre", callback_data="menu_dia_libre"),
            ],
            [
                InlineKeyboardButton("Bajar a amigable", callback_data="menu_apagar_firme"),
                InlineKeyboardButton("Exportar CSV", callback_data="menu_exportar"),
            ],
            [
                InlineKeyboardButton("Borrar todo", callback_data="menu_borrar"),
            ],
        ]
        await q.message.reply_text(
            "<b>Configuracion</b>",
            reply_markup=InlineKeyboardMarkup(kb),
        )
        return
    if q.data == "menu_quiet":
        await q.message.reply_text(
            "Usa: <code>/quiet_hours HH:MM HH:MM</code>\n"
            "Ej: <code>/quiet_hours 22:00 07:00</code>"
        )
        return
    if q.data == "menu_pausa":
        await q.message.reply_text(
            "Usa: <code>/pausa N</code> para silenciarme N dias.\n"
            "Ej: <code>/pausa 3</code>"
        )
        return
    if q.data == "menu_dia_libre":
        await cmd_dia_libre(_FakeUpdate(q.message, q.from_user), ctx)
        return
    if q.data == "menu_apagar_firme":
        await cmd_apagar_firme(_FakeUpdate(q.message, q.from_user), ctx)
        return
    if q.data == "menu_exportar":
        await cmd_exportar_csv(_FakeUpdate(q.message, q.from_user), ctx)
        return
    if q.data == "menu_borrar":
        # Reutiliza borrar_datos (manda confirmacion).
        await borrar_datos(_FakeUpdate(q.message, q.from_user), ctx)
        return
    if q.data == "menu_recordatorios":
        await _procesar(
            q.message, "Lista mis recordatorios activos", uid, ctx=ctx
        )
        return

    mapping = {
        "onboarding": "Hola, quiero empezar!",
        "entreno": "Quiero registrar mi entrenamiento de hoy",
        "comida": "Quiero registrar lo que comi hoy",
        "sueno": "Quiero registrar como dormi anoche",
        "peso": "Quiero registrar mi peso actual",
        "plan_hoy": "Dame mi plan de hoy: que entreno, que comer, agua",
        "reporte": "Como voy esta semana? Dame mi reporte",
        "historial_peso": "Muestrame mi historial de peso",
        "compromiso": "Quiero ver o firmar mi compromiso",
        "cambiar_tono": "Quiero cambiar el tono del coach",
    }
    texto = mapping.get(q.data, "Hola")
    await q.message.chat.send_action(ChatAction.TYPING)
    await _procesar(q.message, texto, uid, ctx=ctx)


_CAPTION_COMPROBANTE = re.compile(
    r"\b(pago|comprobante|bre\W?b|transferencia|nequi|daviplata|pse|recibo)\b",
    re.IGNORECASE,
)


def _tipo_comida_por_hora(hora: int) -> str:
    """Mapea hora local del usuario al tipo de comida mas probable.

    Usado para clasificar fotos de comida sin meta-info. Antes hardcoded
    "almuerzo" lo cual desfiguraba estadisticas (e.g. foto a las 10pm
    quedaba como almuerzo).
    """
    if 5 <= hora < 11:
        return "desayuno"
    if 11 <= hora < 15:
        return "almuerzo"
    if 15 <= hora < 17:
        return "snack"
    if 17 <= hora < 22:
        return "cena"
    return "snack"


async def recibir_foto(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Recibe foto del usuario.

    Si es comprobante de pago (esperando_comprobante=True o caption indica pago)
    -> procesa con Vision-comprobante. Si no, va a Vision-comida.
    Cap 3 fotos/dia free.
    """
    from datetime import date

    from src.db.repository import es_plan_minimo
    from src.db.models import PlanSuscripcion
    from src.services.comprobantes import (
        extraer_datos_comprobante,
        sha256_imagen,
    )
    from src.services.deteccion_duplicados import es_duplicado
    from src.services.vision import (
        analizar_comida,
        describir_imagen_no_comida,
        resize_si_pesa,
    )

    uid = update.effective_user.id
    if not await check_rate_limit(uid):
        await update.message.reply_text("Tranquilo, dame un segundo.")
        return
    puede, usado, limite = await check_daily_quota(uid)
    if not puede:
        await update.message.reply_text(
            f"Llegaste a tu limite diario ({limite} mensajes). "
            "Mejora tu plan con /pagar para seguir entrenando."
        )
        return

    caption = (update.message.caption or "").strip()
    esperando_pago = bool(ctx.user_data.get("esperando_comprobante", False))
    es_modo_pago = esperando_pago or bool(
        caption and _CAPTION_COMPROBANTE.search(caption)
    )

    if es_modo_pago:
        await _procesar_comprobante(update, ctx, uid)
        return

    es_starter_o_mas = await es_plan_minimo(uid, PlanSuscripcion.STARTER)
    if not es_starter_o_mas:
        n = await contar_fotos_hoy(uid)
        if n >= 3:
            logger.info("photo_limit uid=%s n=%d/3 BLOQUEADO", uid, n)
            await update.message.reply_text(
                "Llegaste al limite de 3 fotos/dia en plan Free. "
                "Manana puedes mas, o mejora tu plan con /pagar"
            )
            return
        if n == 2:
            logger.info("photo_limit uid=%s n=%d/3 ULTIMA", uid, n)

    user = await obtener_usuario(uid)
    if not user:
        return
    objetivo = user.objetivo or "mantenerse"
    tono = user.tono.value if user.tono else "firme"
    tz_name = user.timezone or "America/Bogota"
    try:
        ahora_user = datetime.now(ZoneInfo(tz_name))
    except Exception:
        ahora_user = datetime.now(ZoneInfo("America/Bogota"))
    tipo_comida = _tipo_comida_por_hora(ahora_user.hour)
    fecha_user = ahora_user.date().isoformat()

    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        raw = bytes(await file.download_as_bytearray())
        raw = resize_si_pesa(raw)
    except Exception:
        logger.exception("Error descargando foto uid=%s", uid)
        await update.message.reply_text("No pude descargar la foto. Intenta de nuevo.")
        return

    if caption:
        logger.info(
            "recibir_foto con caption uid=%s len=%d preview=%r",
            uid, len(caption), caption[:60],
        )
    result = await analizar_comida(
        raw, objetivo_usuario=objetivo, tono=tono, caption=caption
    )
    if "error" in result:
        # Antes respondiamos con texto fijo y dejabamos al usuario colgado.
        # Ahora delegamos al agente con contexto explicito para que decida
        # apropiadamente. Usamos un segundo analisis para describir que hay.
        err = result["error"]
        descripcion = ""
        if err == "no_food":
            descripcion = await describir_imagen_no_comida(raw)

        logger.info(
            "photo error delegado al coach uid=%s error=%s tiene_caption=%s desc=%r",
            uid, err, bool(caption), descripcion,
        )
        contexto_partes = [
            "[CONTEXTO_FOTO]",
            f"El usuario te envio una foto pero el analizador no detecto comida (error={err}).",
        ]
        if descripcion:
            contexto_partes.append(f"Lo que se ve en la foto: {descripcion}")
        if caption:
            contexto_partes.append(f"Caption del usuario: {caption!r}.")

        contexto_partes.append(
            "Responde al usuario de forma natural segun lo que se ve en la foto. "
            "Si es un producto/etiqueta, pidele info textual si falta. "
            "Si es de entreno, comenta algo motivador o tecnico sobre lo que ves. "
            "Si no tiene nada que ver con fitness/nutricion, aclara que solo procesas "
            "fotos de comida, etiquetas o entrenos."
        )
        contexto = " ".join(contexto_partes)
        await _procesar(update.message, contexto, uid, ctx=ctx)
        return

    # Saneamos lo que viene de Vision (puede devolver dict en alimentos).
    alimentos_raw = result.get("alimentos") or []
    alimentos_clean: list[str] = []
    for item in alimentos_raw:
        if isinstance(item, str):
            s = item.strip()
            if s:
                alimentos_clean.append(s[:80])
        elif isinstance(item, dict):
            nombre = (
                item.get("nombre")
                or item.get("name")
                or item.get("alimento")
                or item.get("item")
                or ""
            )
            if isinstance(nombre, str) and nombre.strip():
                alimentos_clean.append(nombre.strip()[:80])

    calorias = int(result.get("calorias") or 0)
    proteinas = float(result.get("proteinas_g") or 0)
    carbs = float(result.get("carbohidratos_g") or 0)
    grasas = float(result.get("grasas_g") or 0)
    feedback_txt = (result.get("feedback") or "").strip()

    # Log de la intencion ANTES de guardar para tener trazabilidad incluso
    # si los inserts fallan (bug detectado en auditoria: comidas=0,
    # feedback_comida=0 pese a que el bot respondia con macros).
    logger.info(
        "photo_meal flow uid=%s tipo=%s fecha=%s n_alim=%d kcal=%d "
        "P=%.1f C=%.1f G=%.1f",
        uid, tipo_comida, fecha_user, len(alimentos_clean),
        calorias, proteinas, carbs, grasas,
    )

    # Guardamos en 3 pasos separados para que la falla de uno NO mate los
    # otros. Antes un solo try englobaba los 3 y un error temprano dejaba
    # la DB vacia.
    feedback_ok = False
    try:
        await guardar_feedback_comida(
            uid,
            foto_file_id=photo.file_id,
            alimentos=alimentos_clean,
            calorias=calorias,
            proteinas=proteinas,
            carbs=carbs,
            grasas=grasas,
            feedback_texto=feedback_txt,
        )
        feedback_ok = True
    except Exception:
        logger.exception(
            "photo_meal: guardar_feedback_comida fallo uid=%s n_alim=%d kcal=%d",
            uid, len(alimentos_clean), calorias,
        )

    comida_ok = False
    try:
        await guardar_comida(
            uid,
            fecha_user,
            tipo_comida,
            alimentos_clean,
            calorias=calorias,
            proteinas=proteinas,
            carbs=carbs,
            grasas=grasas,
        )
        comida_ok = True
    except Exception:
        logger.exception(
            "photo_meal: guardar_comida fallo uid=%s tipo=%s fecha=%s "
            "alimentos=%r",
            uid, tipo_comida, fecha_user, alimentos_clean[:5],
        )

    try:
        await log_evento(
            uid,
            "photo_meal",
            {
                "calorias": calorias,
                "tipo": tipo_comida,
                "fecha": fecha_user,
                "feedback_ok": feedback_ok,
                "comida_ok": comida_ok,
                "n_alimentos": len(alimentos_clean),
            },
        )
    except Exception:
        logger.exception("photo_meal: log_evento fallo uid=%s", uid)

    alimentos = ", ".join(result.get("alimentos", [])) or "alimentos"
    respuesta = (
        f"<b>Detecte:</b> {alimentos}\n"
        f"<b>~{result.get('calorias', 0)} kcal</b> "
        f"(P {result.get('proteinas_g', 0):.0f}g / "
        f"C {result.get('carbohidratos_g', 0):.0f}g / "
        f"G {result.get('grasas_g', 0):.0f}g)\n\n"
        f"{result.get('feedback', '')}"
    )
    await update.message.reply_text(respuesta)


async def recibir_voz(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Recibe nota de voz / audio, transcribe con Whisper y procesa como texto.

    Acepta `message.voice` (notas grabadas en Telegram) y `message.audio`
    (archivos enviados). Reaplica el mismo flujo que `mensaje()`: crisis,
    rate-limit, escalation y `_procesar`.
    """
    from src.services.tts import transcribir_audio

    uid = update.effective_user.id
    voice = update.message.voice or update.message.audio
    if voice is None:
        return

    if not await check_rate_limit(uid):
        await update.message.reply_text("Tranquilo, dame un segundo.")
        return
    puede, usado, limite = await check_daily_quota(uid)
    if not puede:
        await update.message.reply_text(
            f"Llegaste a tu limite diario ({limite} mensajes). "
            "Mejora tu plan con /pagar para seguir entrenando."
        )
        return

    duration = getattr(voice, "duration", 0) or 0
    if duration > 300:
        await update.message.reply_text(
            "Ese audio es muy largo (limite 5 min). Mandame uno mas corto."
        )
        return

    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        file = await ctx.bot.get_file(voice.file_id)
        audio_bytes = bytes(await file.download_as_bytearray())
    except Exception:
        logger.exception("Error descargando audio uid=%s", uid)
        await update.message.reply_text("No pude descargar tu audio. Intenta de nuevo.")
        return

    if not audio_bytes:
        await update.message.reply_text("El audio llego vacio. Intenta de nuevo.")
        return

    file_path = getattr(file, "file_path", "") or ""
    filename = file_path.rsplit("/", 1)[-1] or "voice.ogg"

    texto = await transcribir_audio(audio_bytes, filename=filename)
    if not texto:
        await update.message.reply_text(
            "No pude entender tu audio. Intenta hablar mas claro o mandame texto."
        )
        return

    logger.info(
        "Audio transcrito uid=%s dur=%ss bytes=%d preview=%r",
        uid,
        duration,
        len(audio_bytes),
        texto[:120],
    )
    await log_evento(
        uid,
        "audio_transcrito",
        {"duracion_s": duration, "chars": len(texto)},
    )

    user = await obtener_o_crear_usuario(uid)
    pais = user.pais if user else "CO"
    peso = user.peso_kg if user else None
    crisis = detectar_crisis(texto[:8000], pais=pais, peso_actual_kg=peso)
    if crisis is not None:
        try:
            sent = await update.message.reply_text(crisis.mensaje_contenedor)
            await log_crisis(
                uid,
                nivel=crisis.nivel,
                keywords=crisis.keywords,
                mensaje_usuario=texto[:500],
                mensaje_enviado_id=sent.message_id,
                derivado_a=crisis.lineas_crisis[:120],
            )
            await log_evento(uid, "crisis_detected", {"nivel": crisis.nivel, "via": "voz"})
        except Exception:
            logger.exception("Error manejando crisis (voz) uid=%s", uid)
        return

    await reaccionar(update.message, ctx)

    if _CONFIRMACION_ENTRENO.search(texto):
        try:
            from src.telegram.escalation import cancelar_escalado_hoy

            await cancelar_escalado_hoy(uid, ctx, "entreno")
        except ImportError:
            pass

    await _procesar(update.message, texto, uid, ctx=ctx)


async def _procesar_comprobante(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE, uid: int
) -> None:
    """Procesa una foto como comprobante de pago.

    Flujo: Vision analiza -> guarda SIEMPRE en DB -> duplicados -> activacion.

    IMPORTANTE: el comprobante se guarda en la DB incluso si Vision no lo
    reconoce como comprobante valido. Asi el admin siempre puede revisarlo
    manualmente desde /admin/pagos. Antes del fix, si Vision decia
    "no es comprobante", no se guardaba nada y el pago se perdia.
    """
    from src.db.models import DuracionPago, PlanSuscripcion
    from src.services.comprobantes import (
        extraer_datos_comprobante,
        sha256_imagen,
    )
    from src.services.deteccion_duplicados import es_duplicado
    from src.services.pricing import dias_duracion, formatear_precio, precio_cop

    pendiente = ctx.user_data.get("plan_pendiente_pago") or {}
    plan_str = pendiente.get("plan", "starter")
    duracion_str = pendiente.get("duracion", "mensual")
    try:
        plan_solicitado = PlanSuscripcion(plan_str)
        duracion = DuracionPago(duracion_str)
    except ValueError:
        plan_solicitado = PlanSuscripcion.STARTER
        duracion = DuracionPago.MENSUAL

    monto_esperado = pendiente.get("monto") or precio_cop(plan_solicitado, duracion)
    dias_otorgados = dias_duracion(plan_solicitado, duracion)

    await update.message.chat.send_action(ChatAction.TYPING)
    await update.message.reply_text(
        "Recibi tu comprobante. Lo estoy analizando..."
    )

    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        raw = bytes(await file.download_as_bytearray())
    except Exception:
        logger.exception("Error descargando comprobante uid=%s", uid)
        await update.message.reply_text("No pude descargar el comprobante. Intenta de nuevo.")
        return

    sha = sha256_imagen(raw)

    datos = await extraer_datos_comprobante(raw)
    vision_reconocio = datos.get("ok") and datos.get("es_comprobante")

    # Si Vision no reconocio la imagen, igual guardamos con datos vacios
    # para que el admin pueda revisarla manualmente.
    if not vision_reconocio:
        datos_para_guardar = {
            "monto_cop": 0,
            "monto_extraido_raw": "",
            "referencia": "",
            "cuenta_origen": "",
            "cuenta_destino": "",
            "fecha_pago": None,
            "hora_pago": None,
            "metodo": "otro",
            "confianza": 0.0,
            "raw": datos.get("raw", {}),
            "vision_rechazado": True,
            "razon_rechazo": datos.get("razon", "no_reconocido"),
        }
    else:
        datos_para_guardar = datos
        datos_para_guardar["vision_rechazado"] = False

    # GUARDAR SIEMPRE en DB (antes solo se guardaba si Vision decia OK)
    try:
        comprobante = await guardar_comprobante(
            telegram_id=uid,
            foto_file_id=photo.file_id,
            foto_sha256=sha,
            plan_solicitado=plan_solicitado,
            duracion=duracion,
            monto_esperado_cop=monto_esperado,
            dias_otorgados=dias_otorgados,
            vision_payload=datos_para_guardar,
            referido_codigo=pendiente.get("referido_codigo"),
        )
    except Exception:
        logger.exception("Error guardando comprobante uid=%s sha=%s", uid, sha[:12])
        await update.message.reply_text(
            "Hubo un error guardando tu comprobante. "
            "Intenta de nuevo en un momento o contacta soporte."
        )
        return
    logger.info(
        "comprobante guardado uid=%s comp_id=%s vision_ok=%s",
        uid, comprobante.id, vision_reconocio,
    )

    # NOTIFICAR AL ADMIN con botones inline para aprobar/rechazar desde Telegram
    admin_base = str(settings.landing_url or "https://entrenadorax.axsoftware.codes").rstrip("/")
    admin_link = f"{admin_base}/admin/pagos/{comprobante.id}"
    if settings.developer_chat_id:
        try:
            status_label = "Vision OK" if vision_reconocio else "Vision NO reconocio"
            monto_label = formatear_precio(comprobante.monto_cop) if comprobante.monto_cop else "no detectado"
            admin_keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "Aprobar pago",
                        callback_data=f"admin_aprobar:{comprobante.id}",
                    ),
                    InlineKeyboardButton(
                        "Rechazar",
                        callback_data=f"admin_rechazar:{comprobante.id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "Ver en panel web",
                        url=admin_link,
                    ),
                ],
            ])
            await ctx.bot.send_photo(
                chat_id=settings.developer_chat_id,
                photo=photo.file_id,
                caption=(
                    f"<b>Nuevo comprobante #{comprobante.id}</b>\n"
                    f"Usuario: uid={uid}\n"
                    f"Plan: {plan_solicitado.value} ({duracion.value})\n"
                    f"Monto: {monto_label} (esperado {formatear_precio(monto_esperado)})\n"
                    f"Vision: {status_label}\n"
                    f"Match: {'si' if comprobante.monto_match else 'no'}"
                ),
                reply_markup=admin_keyboard,
            )
        except Exception:
            logger.exception("No pude notificar admin de comprobante uid=%s", uid)

    # Si Vision no lo reconocio: notificar al usuario pero el pago queda
    # en la cola del admin para revision manual.
    if not vision_reconocio:
        razon = datos.get("razon", "no_reconocido")
        # LIMPIAR ESTADO CONVERSACIONAL PARA EVITAR BUCLES INFINITOS
        ctx.user_data.pop("esperando_comprobante", None)
        ctx.user_data.pop("plan_pendiente_pago", None)
        
        await update.message.reply_text(
            "He guardado tu comprobante de pago de forma segura para que el administrador lo revise manualmente.\n\n"
            "<b>No es necesario que vuelvas a enviar la imagen.</b> Tu pago ya está en cola de aprobación manual y te notificaremos por este medio tan pronto como sea validado (usualmente toma menos de 24 horas).\n\n"
            "¡Muchas gracias por tu paciencia!"
        )
        await log_evento(uid, "comprobante_vision_rechazado", {
            "razon": razon, "comp_id": comprobante.id,
        })
        return

    # Vision reconocio: flujo normal (duplicados + activacion)
    dup = await es_duplicado(
        foto_sha256=sha,
        monto_cop=datos.get("monto_cop", 0),
        fecha_pago=datos.get("fecha_pago"),
        referencia=datos.get("referencia", ""),
        cuenta_origen=datos.get("cuenta_origen", ""),
    )

    if dup.get("es_duplicado"):
        await marcar_comprobante_duplicado(comprobante.id, dup["razon"])
        await update.message.reply_text(
            "Este comprobante ya habia sido enviado antes (razon: "
            f"{dup['razon']}). No puedo activar tu plan dos veces con el mismo "
            "pago. Si crees que es un error, contacta soporte."
        )
        await log_evento(uid, "comprobante_duplicado", {"razon": dup["razon"]})
        return

    monto_match = comprobante.monto_match
    if monto_match:
        await activar_plan(
            telegram_id=uid,
            plan=plan_solicitado,
            dias=dias_otorgados,
            duracion=duracion,
            metodo=comprobante.metodo,
            monto_cop=comprobante.monto_cop,
            comprobante_id=comprobante.id,
        )
        ctx.user_data.pop("esperando_comprobante", None)
        ctx.user_data.pop("plan_pendiente_pago", None)
        await update.message.reply_text(
            f"<b>Pago recibido!</b> Plan <b>{plan_solicitado.value}</b> "
            f"activado provisional. Un admin lo validara en las proximas horas.\n\n"
            f"Monto detectado: {formatear_precio(comprobante.monto_cop)}\n"
            f"Referencia: <code>{comprobante.referencia}</code>"
        )
    else:
        await update.message.reply_text(
            f"Recibi tu comprobante pero el monto no coincide.\n"
            f"Esperado: {formatear_precio(monto_esperado)}\n"
            f"Detectado: {formatear_precio(comprobante.monto_cop)}\n\n"
            "Un admin va a revisarlo. Te aviso cuando se valide."
        )

    await log_evento(
        uid,
        "comprobante_recibido",
        {
            "comp_id": comprobante.id,
            "monto_cop": comprobante.monto_cop,
            "monto_match": monto_match,
            "plan": plan_solicitado.value,
        },
    )

    if settings.developer_chat_id:
        try:
            estado = "activacion_provisional" if monto_match else "monto_no_match"
            await ctx.bot.send_message(
                chat_id=settings.developer_chat_id,
                text=(
                    f"<b>Nuevo comprobante #{comprobante.id}</b>\n"
                    f"uid={uid} plan={plan_solicitado.value}\n"
                    f"monto: {comprobante.monto_cop}/{monto_esperado}\n"
                    f"metodo: {comprobante.metodo.value}\n"
                    f"ref: <code>{comprobante.referencia}</code>\n"
                    f"estado: {estado}"
                ),
            )
        except Exception:
            logger.exception("No pude notificar admin de nuevo comprobante")


@requiere_tier(PlanSuscripcion.STARTER)
async def cmd_mi_mes(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Genera y envia PDF con analisis del mes pasado."""
    from datetime import date as _date
    from io import BytesIO

    from src.services.analisis_mensual import generar_pdf_mensual

    uid = update.effective_user.id
    hoy = _date.today()
    if hoy.month == 1:
        ano, mes = hoy.year - 1, 12
    else:
        ano, mes = hoy.year, hoy.month - 1

    await update.message.chat.send_action(ChatAction.UPLOAD_DOCUMENT)
    try:
        pdf_bytes = await generar_pdf_mensual(uid, ano, mes)
        if not pdf_bytes:
            await update.message.reply_text(
                "Aun no tengo datos suficientes del mes pasado."
            )
            return
        await ctx.bot.send_document(
            chat_id=uid,
            document=BytesIO(pdf_bytes),
            filename=f"entrenadorax_{ano}-{mes:02d}.pdf",
            caption=f"<b>Tu mes en EntrenadorAX</b>: {mes:02d}/{ano}",
        )
        await log_evento(uid, "pdf_mensual_enviado", {"ano": ano, "mes": mes})
    except Exception:
        logger.exception("Error generando PDF mensual uid=%s", uid)
        await update.message.reply_text(
            "No pude generar el PDF ahora. Intenta de nuevo en unos minutos."
        )


@requiere_tier(PlanSuscripcion.STARTER)
async def cmd_llamar(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Abre Mini App en modo llamada con el coach."""
    from telegram import WebAppInfo

    if not settings.miniapp_url:
        await update.message.reply_text(
            "El servicio de llamada esta proximamente. Mientras tanto, "
            "responde con texto que tambien te ayudo."
        )
        return
    url = f"{str(settings.miniapp_url).rstrip('/')}/llamar"
    keyboard = [[
        InlineKeyboardButton("Iniciar llamada", web_app=WebAppInfo(url=url)),
    ]]
    await update.message.reply_text(
        "<b>Llamar al coach</b>\n\nToca el boton y permite acceso al microfono.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cmd_agua(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Registra agua o consulta consumo del dia. /agua [ml]."""
    from src.services.hidratacion import consumo_hoy_ml, objetivo_ml, registrar_agua

    uid = update.effective_user.id
    args = ctx.args or []
    if args:
        try:
            ml = int(args[0])
            ml = max(50, min(2000, ml))
        except ValueError:
            await update.message.reply_text("Uso: <code>/agua 500</code> (en ml)")
            return
        await registrar_agua(uid, ml)
        await log_evento(uid, "agua_registrada", {"ml": ml})
    consumido = await consumo_hoy_ml(uid)
    objetivo = await objetivo_ml(uid)
    pct = int(consumido / objetivo * 100) if objetivo else 0
    bar_full = min(10, pct // 10)
    bar = "*" * bar_full + "-" * (10 - bar_full)
    keyboard = [
        [
            InlineKeyboardButton("+250ml", callback_data="agua:250"),
            InlineKeyboardButton("+500ml", callback_data="agua:500"),
            InlineKeyboardButton("+750ml", callback_data="agua:750"),
        ]
    ]
    await update.message.reply_text(
        f"<b>Hidratacion hoy</b>\n"
        f"{consumido}ml / {objetivo}ml ({pct}%)\n"
        f"<code>[{bar}]</code>",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cmd_calma(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista sesiones de mindfulness disponibles."""
    from src.services.mindfulness import listar_sesiones

    keyboard = [
        [InlineKeyboardButton(s["titulo"], callback_data=f"calma:{s['slug']}")]
        for s in listar_sesiones()
    ]
    await update.message.reply_text(
        "<b>Sesiones de calma</b>\n\nElige una:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cmd_desafios(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista desafios activos + boton inscribirse."""
    from src.services.comunidad import listar_desafios_activos

    desafios = await listar_desafios_activos()
    if not desafios:
        await update.message.reply_text(
            "No hay desafios activos ahora. Vuelve a chequear pronto!"
        )
        return
    lineas = ["<b>Desafios activos:</b>"]
    botones = []
    for d in desafios[:10]:
        lineas.append(f"- <b>{d.titulo}</b> ({d.tipo}) hasta {d.fecha_fin.isoformat()}")
        botones.append([
            InlineKeyboardButton(
                f"Inscribirme: {d.titulo[:30]}",
                callback_data=f"desafio_inscribir:{d.slug}",
            )
        ])
    await update.message.reply_text(
        "\n".join(lineas), reply_markup=InlineKeyboardMarkup(botones)
    )


async def cmd_ranking(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra mi posicion en desafios activos."""
    from src.services.comunidad import mi_posicion

    uid = update.effective_user.id
    posiciones = await mi_posicion(uid)
    if not posiciones:
        await update.message.reply_text(
            "No estas inscrito en ningun desafio. Usa /desafios para ver disponibles."
        )
        return
    lineas = ["<b>Tu posicion en desafios:</b>"]
    for p in posiciones:
        lineas.append(
            f"- <b>{p['desafio']}</b>: posicion <b>#{p['posicion']}</b> con valor {p['valor']:.0f}"
        )
    await update.message.reply_text("\n".join(lineas))


async def cmd_kudos(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/kudos @usuario - dar kudos a otro atleta."""
    from src.services.comunidad import dar_kudos

    args = ctx.args or []
    if not args:
        await update.message.reply_text(
            "Uso: <code>/kudos @username</code>\nDa 1 kudos a otro atleta (max 10/dia)."
        )
        return
    target = args[0].lstrip("@")
    try:
        chat = await ctx.bot.get_chat(f"@{target}")
        destino_id = chat.id
    except Exception:
        await update.message.reply_text(
            "No encontre ese usuario. Asegurate de poner el @username correcto."
        )
        return
    uid = update.effective_user.id
    ok = await dar_kudos(uid, destino_id)
    if ok:
        await update.message.reply_text(f"Kudos a @{target} dado!")
    else:
        await update.message.reply_text(
            "No pude dar kudos (puede ser que ya llegaste al cap diario o el usuario no exista en EntrenadorAX)."
        )


async def cmd_pagar(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra los 4 tiers con inline keyboard para iniciar pago."""
    from src.db.models import DuracionPago, PlanSuscripcion
    from src.services.pricing import formatear_precio, precio_cop

    starter_m = formatear_precio(precio_cop(PlanSuscripcion.STARTER, DuracionPago.MENSUAL))
    pro_m = formatear_precio(precio_cop(PlanSuscripcion.PRO, DuracionPago.MENSUAL))
    elite_m = formatear_precio(precio_cop(PlanSuscripcion.ELITE, DuracionPago.MENSUAL))
    pro_a = formatear_precio(precio_cop(PlanSuscripcion.PRO, DuracionPago.ANUAL))
    lifetime = formatear_precio(precio_cop(PlanSuscripcion.LIFETIME, DuracionPago.LIFETIME))

    keyboard = [
        [InlineKeyboardButton(f"Starter {starter_m}/mes", callback_data="pagar:starter:mensual")],
        [InlineKeyboardButton(f"Pro {pro_m}/mes", callback_data="pagar:pro:mensual")],
        [InlineKeyboardButton(f"Elite {elite_m}/mes", callback_data="pagar:elite:mensual")],
        [InlineKeyboardButton(f"Pro anual {pro_a} (20% off)", callback_data="pagar:pro:anual")],
        [InlineKeyboardButton(f"Lifetime {lifetime}", callback_data="pagar:lifetime:lifetime")],
    ]
    await update.message.reply_text(
        "<b>Elige tu plan EntrenadorAX</b>\n\n"
        f"<b>Starter</b> {starter_m}/mes: charts avanzados + photo ilimitado + Mini App + 5min voz trial.\n"
        f"<b>Pro</b> {pro_m}/mes: + voz coach + 30min Realtime + 1 wearable + plan generator.\n"
        f"<b>Elite</b> {elite_m}/mes: + 120min Realtime + wearables ilimitados + PDFs ilimitados.\n"
        f"<b>Lifetime</b> {lifetime}: Elite para siempre (solo 100 cupos en launch).",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


def registrar(app: Application) -> None:
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("borrar_datos", borrar_datos))
    app.add_handler(CommandHandler("pausa", cmd_pausa))
    app.add_handler(CommandHandler("porque_me_escribiste", cmd_porque_me_escribiste))
    app.add_handler(CommandHandler("ayuda", cmd_ayuda))
    app.add_handler(CommandHandler("tono", cmd_tono))
    app.add_handler(CommandHandler("quiet_hours", cmd_quiet_hours))
    app.add_handler(CommandHandler("apagar_firme", cmd_apagar_firme))
    app.add_handler(CommandHandler("salir", cmd_salir))
    app.add_handler(CommandHandler("dia_libre", cmd_dia_libre))
    app.add_handler(CommandHandler("feedback", cmd_feedback))
    app.add_handler(CommandHandler("codigo_web", cmd_codigo_web))
    app.add_handler(CommandHandler("presumir", cmd_presumir))
    app.add_handler(CommandHandler("hoy", cmd_hoy))
    app.add_handler(CommandHandler("pr", cmd_pr))
    app.add_handler(CommandHandler("reporte", cmd_reporte))
    app.add_handler(CommandHandler("compromiso", cmd_compromiso))
    app.add_handler(CommandHandler("firmar_compromiso", cmd_firmar_compromiso))
    app.add_handler(CommandHandler("peso", cmd_peso))
    app.add_handler(CommandHandler("grafico", cmd_grafico))
    app.add_handler(CommandHandler("exportar_csv", cmd_exportar_csv))
    app.add_handler(CommandHandler("upgrade", cmd_upgrade))
    app.add_handler(CommandHandler("pagar", cmd_pagar))
    app.add_handler(CommandHandler("planes", cmd_pagar))
    app.add_handler(CommandHandler("llamar", cmd_llamar))
    app.add_handler(CommandHandler("mi_mes", cmd_mi_mes))
    app.add_handler(CommandHandler("desafios", cmd_desafios))
    app.add_handler(CommandHandler("ranking", cmd_ranking))
    app.add_handler(CommandHandler("kudos", cmd_kudos))
    app.add_handler(CommandHandler("agua", cmd_agua))
    app.add_handler(CommandHandler("calma", cmd_calma))
    app.add_handler(CommandHandler("invitar", cmd_invitar))
    # Atajos slash que reusan el agente (espejo de los botones del menu).
    # Sin esto, /sueno, /comida, /entreno etc. caen al MessageHandler de
    # texto que ignora el "/" inicial, perdiendo intencion clara del usuario.
    for _slash_name, _slash_prompt in _MENU_SLASH_PROMPTS.items():
        app.add_handler(
            CommandHandler(_slash_name, _make_menu_slash_handler(_slash_prompt))
        )
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    app.add_handler(
        MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler)
    )
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, recibir_voz))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensaje))
    app.add_handler(MessageHandler(filters.PHOTO, recibir_foto))
    app.add_handler(CallbackQueryHandler(boton))

    from src.telegram.quiz import registrar_handlers_quiz

    registrar_handlers_quiz(app)
