"""Handlers de Telegram: comandos, mensajes, callbacks, foto."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date

import telegram.error
from telegram import (
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestChat,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from agents import RunConfig, Runner, SessionSettings
from agents.extensions.memory import RedisSession

from src.cache import limpiar_keys_usuario
from src.coach import coach
from src.config import settings
from src.services.crisis import detectar as detectar_crisis
from src.services.crisis import detectar_diagnostico_output
from src.db.repository import (
    actualizar_usuario,
    aceptar_modo_militar,
    cambiar_tono as repo_cambiar_tono,
    contar_fotos_hoy,
    eliminar_usuario,
    guardar_comida,
    guardar_feedback_comida,
    log_crisis,
    log_evento,
    marcar_bot_bloqueado,
    obtener_compromiso_activo,
    obtener_o_crear_usuario,
    obtener_o_crear_streak,
    obtener_usuario,
    pausar_recordatorios,
    set_quiet_hours,
    ultimos_eventos,
    usar_freeze_streak,
)
from src.telegram.middlewares import check_rate_limit
from src.telegram.reacciones import reaccionar

logger = logging.getLogger(__name__)

RUN_CONFIG = RunConfig(session_settings=SessionSettings(limit=settings.session_limit))


QUICK_ACTIONS_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("Entrene"), KeyboardButton("Comi")],
        [KeyboardButton("Dormi"), KeyboardButton("Peso")],
        [KeyboardButton("Mi semana"), KeyboardButton("Plan de hoy")],
    ],
    is_persistent=True,
    resize_keyboard=True,
    input_field_placeholder="Escribi o tap",
)


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


async def _build_prompt(texto: str, uid: int) -> str:
    """Construye el prompt con perfil + tono + compromiso + streak inyectados."""
    user = await obtener_o_crear_usuario(uid)
    perfil_parts = [
        f"uid={uid}",
        f"fecha={date.today().isoformat()}",
        f"tono={user.tono.value if user.tono else 'firme'}",
    ]
    if user.nombre:
        perfil_parts.append(f"nombre={user.nombre}")
    if user.peso_kg:
        perfil_parts.append(f"peso={user.peso_kg}kg")
    if user.altura_cm:
        perfil_parts.append(f"altura={user.altura_cm}cm")
    if user.edad:
        perfil_parts.append(f"edad={user.edad}")
    if user.objetivo:
        perfil_parts.append(f"objetivo={user.objetivo}")
    if user.nivel:
        perfil_parts.append(f"nivel={user.nivel}")
    if user.dias_entreno:
        perfil_parts.append(f"dias_entreno={user.dias_entreno}")
    if user.deporte_principal:
        perfil_parts.append(f"deporte={user.deporte_principal}")
    if user.timezone:
        perfil_parts.append(f"tz={user.timezone}")
    perfil_parts.append(
        f"onboarding={'si' if user.onboarding_completo else 'no'}"
    )
    compromiso = await obtener_compromiso_activo(uid)
    if compromiso:
        perfil_parts.append(
            f"compromiso='{compromiso.objetivo_texto[:80]}' (deadline={compromiso.deadline.isoformat()})"
        )
    try:
        streak = await obtener_o_crear_streak(uid, "entreno")
        perfil_parts.append(f"streak_entreno={streak.dias_actuales}")
    except Exception:
        pass
    if user.pausado_hasta and user.pausado_hasta >= date.today():
        perfil_parts.append(f"pausado_hasta={user.pausado_hasta.isoformat()}")
    return f"[{' | '.join(perfil_parts)}] {texto}"


async def _procesar(
    message,
    texto: str,
    uid: int,
    with_keyboard: bool = False,
    ctx: ContextTypes.DEFAULT_TYPE | None = None,
) -> None:
    """Ejecuta el agente con sesion Redis. Sesion DB cerrada antes del LLM.
    Cancela escalation de los tipos que el usuario cumplio durante el run.
    """
    prompt = await _build_prompt(texto, uid)
    session = RedisSession.from_url(
        str(uid),
        url=settings.redis_url_str,
        ttl=settings.session_ttl_seconds,
    )
    try:
        result = await Runner.run(
            coach, prompt, session=session, run_config=RUN_CONFIG
        )
        output = result.final_output

        diag = detectar_diagnostico_output(output)
        if diag:
            logger.warning("Output guardrail: diagnostico detectado uid=%s: %s", uid, diag)
            output = (
                "Note algo en mi respuesta que prefiero no afirmar. Lo correcto es "
                "que un profesional medico/nutricionista/psicologo evalue tu caso. "
                "Sigamos con habitos concretos: que vamos a hacer hoy?"
            )
            await log_evento(uid, "output_guardrail_diagnostico", {"matches": diag[:5]})

        chunks = [output[i : i + 4000] for i in range(0, len(output), 4000)] or [""]
        for i, chunk in enumerate(chunks):
            kwargs = {}
            if with_keyboard and i == len(chunks) - 1:
                kwargs["reply_markup"] = QUICK_ACTIONS_KEYBOARD
            await _enviar_con_retry(message, chunk, **kwargs)

        if ctx is not None and ctx.job_queue is not None:
            await _autocancelar_escalation_si_cumplio(uid, ctx)
    except Exception:
        logger.exception("Error procesando mensaje uid=%s", uid)
        await _enviar_con_retry(
            message, "Ups, tuve un problema procesando tu mensaje. Intentalo de nuevo."
        )
    finally:
        await session.close()


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

    user = await obtener_usuario(uid)
    pais = user.pais if user else "CO"
    crisis = detectar_crisis(texto, pais=pais)
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
    keyboard = [
        [
            InlineKeyboardButton("Registrar entreno", callback_data="entreno"),
            InlineKeyboardButton("Registrar comida", callback_data="comida"),
        ],
        [
            InlineKeyboardButton("Como dormi", callback_data="sueno"),
            InlineKeyboardButton("Mi peso actual", callback_data="peso"),
        ],
        [
            InlineKeyboardButton("Reporte semanal", callback_data="reporte"),
            InlineKeyboardButton("Historial de peso", callback_data="historial_peso"),
        ],
        [
            InlineKeyboardButton("Mi compromiso", callback_data="compromiso"),
            InlineKeyboardButton("Cambiar tono", callback_data="cambiar_tono"),
        ],
    ]
    await update.message.reply_text(
        "Que quieres hacer?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    await update.message.reply_text(
        "Tip: usa los botones de abajo siempre que quieras.",
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
        "1) Escribime cualquier cosa: 'hice pierna hoy, 4x8 sentadilla 80kg', "
        "'almorce pollo y arroz', 'dormi 7h', 'peso 82kg'.\n"
        "2) Yo te recuerdo entrenar, comer y dormir si no lo haces.\n"
        "3) Mientras mas faltes a tu compromiso, mas intenso me pongo.\n"
        "4) Comandos clave:\n"
        "   /menu - acciones rapidas\n"
        "   /tono - cambiar entre amigable/firme/militar\n"
        "   /pausa N - silenciarme N dias\n"
        "   /compromiso - ver mi pacto contigo\n"
        "   /pr - mis personal records\n"
        "   /reporte - resumen semanal\n"
        "   /ayuda - este texto\n"
        "   /salir - bajar tono y reducir mensajes\n"
        "   /borrar_datos - eliminar todo\n\n"
        "<b>Privacidad:</b> tus datos viven en tu instancia. Puedes borrar todo "
        "cuando quieras con /borrar_datos."
    )


async def boton(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

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

    if q.data == "confirmar_borrado":
        try:
            borrado = await eliminar_usuario(uid)
            await limpiar_keys_usuario(uid)
            await log_evento(uid, "borrar_datos", {"existia": borrado})
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
        except Exception:
            logger.exception("Error borrando datos uid=%s", uid)
            await q.edit_message_text(
                "Hubo un error eliminando tus datos. Intenta de nuevo en un momento."
            )
        return

    mapping = {
        "onboarding": "Hola, quiero empezar!",
        "entreno": "Quiero registrar mi entrenamiento de hoy",
        "comida": "Quiero registrar lo que comi hoy",
        "sueno": "Quiero registrar como dormi anoche",
        "peso": "Quiero registrar mi peso actual",
        "reporte": "Como voy esta semana? Dame mi reporte",
        "historial_peso": "Muestrame mi historial de peso",
        "compromiso": "Quiero ver o firmar mi compromiso",
        "cambiar_tono": "Quiero cambiar el tono del coach",
    }
    texto = mapping.get(q.data, "Hola")
    await q.message.chat.send_action(ChatAction.TYPING)
    await _procesar(q.message, texto, uid, ctx=ctx)


async def recibir_foto(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Recibe foto del usuario. Si es comida, llama Vision API. Cap 3 fotos/dia free."""
    from datetime import date

    from src.db.repository import es_usuario_pro
    from src.services.vision import analizar_comida, resize_si_pesa

    uid = update.effective_user.id
    if not await check_rate_limit(uid):
        await update.message.reply_text("Tranquilo, dame un segundo.")
        return

    es_pro = await es_usuario_pro(uid)
    if not es_pro:
        n = await contar_fotos_hoy(uid)
        if n >= 3:
            await update.message.reply_text(
                "Llegaste al limite de 3 fotos/dia en plan free. "
                "Manana puedes mas, o /upgrade para Pro."
            )
            return

    user = await obtener_usuario(uid)
    if not user:
        return
    objetivo = user.objetivo or "mantenerse"
    tono = user.tono.value if user.tono else "firme"

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

    result = await analizar_comida(raw, objetivo_usuario=objetivo, tono=tono)
    if "error" in result:
        if result["error"] == "no_food":
            await update.message.reply_text(
                "No detecto comida en esa foto. Mandame foto de tu plato y te ayudo."
            )
        else:
            await update.message.reply_text(
                "Hubo un problema analizando la foto. Intenta de nuevo en un momento."
            )
        return

    try:
        await guardar_feedback_comida(
            uid,
            foto_file_id=photo.file_id,
            alimentos=result.get("alimentos", []),
            calorias=result.get("calorias", 0),
            proteinas=result.get("proteinas_g", 0),
            carbs=result.get("carbohidratos_g", 0),
            grasas=result.get("grasas_g", 0),
            feedback_texto=result.get("feedback", ""),
        )
        await guardar_comida(
            uid,
            date.today().isoformat(),
            "almuerzo",
            result.get("alimentos", []),
            calorias=result.get("calorias", 0),
            proteinas=result.get("proteinas_g", 0),
            carbs=result.get("carbohidratos_g", 0),
            grasas=result.get("grasas_g", 0),
        )
        await log_evento(uid, "photo_meal", {"calorias": result.get("calorias", 0)})
    except Exception:
        logger.exception("Error guardando feedback uid=%s", uid)

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
    app.add_handler(CommandHandler("presumir", cmd_presumir))
    app.add_handler(CommandHandler("hoy", cmd_hoy))
    app.add_handler(CommandHandler("pr", cmd_pr))
    app.add_handler(CommandHandler("reporte", cmd_reporte))
    app.add_handler(CommandHandler("compromiso", cmd_compromiso))
    app.add_handler(CommandHandler("firmar_compromiso", cmd_firmar_compromiso))
    app.add_handler(CommandHandler("peso", cmd_peso))
    app.add_handler(CommandHandler("grafico", cmd_grafico))
    app.add_handler(CommandHandler("exportar_csv", cmd_exportar_csv))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensaje))
    app.add_handler(MessageHandler(filters.PHOTO, recibir_foto))
    app.add_handler(CallbackQueryHandler(boton))

    from src.telegram.quiz import registrar_handlers_quiz

    registrar_handlers_quiz(app)
