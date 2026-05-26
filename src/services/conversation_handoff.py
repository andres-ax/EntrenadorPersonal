"""Handoff de contexto entre app Android y Telegram."""
from __future__ import annotations

import logging

from openai import AsyncOpenAI

from src.config import settings
from src.db.models import CanalConversacion, RolMensajeChat
from src.config import settings
from src.services.conversation_service import (
    fijar_conversacion_activa,
    guardar_mensaje,
    listar_mensajes,
    obtener_conversacion,
    session_key_for_conversacion,
)
from src.telegram.safe_session import SafeRedisSession
from src.db.connection import async_session_factory
from src.db.models import Conversacion
from sqlalchemy import update

logger = logging.getLogger(__name__)


async def _generar_resumen_handoff(mensajes: list) -> str:
    if not mensajes:
        return "Continuacion de conversacion desde la app (sin mensajes previos)."

    lines = []
    for m in mensajes[-12:]:
        rol = "Usuario" if m.rol == RolMensajeChat.USER else "Coach"
        lines.append(f"{rol}: {m.contenido[:300]}")

    transcript = "\n".join(lines)
    if not settings.openai_api_key:
        return transcript[:800]

    client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
    try:
        resp = await client.chat.completions.create(
            model=settings.coach_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Resume esta conversacion de coaching fitness en espanol (max 600 palabras). "
                        "Incluye: objetivo del hilo, datos registrados, pendientes y tono del usuario."
                    ),
                },
                {"role": "user", "content": transcript},
            ],
            max_tokens=500,
        )
        return (resp.choices[0].message.content or transcript)[:2000]
    except Exception:
        logger.exception("Error generando resumen handoff")
        return transcript[:800]


async def handoff_app_a_telegram(
    conversacion_id: int,
    user_id: int,
    telegram_id: int,
    bot,
) -> dict:
    """Genera resumen y notifica al usuario en Telegram."""
    conv = await obtener_conversacion(conversacion_id, user_id)
    if conv is None:
        raise ValueError("Conversacion no encontrada")

    mensajes = await listar_mensajes(conversacion_id, limit=30)
    resumen = await _generar_resumen_handoff(mensajes)

    async with async_session_factory() as session:
        await session.execute(
            update(Conversacion)
            .where(Conversacion.id == conversacion_id)
            .values(resumen_handoff=resumen, canal_creador=CanalConversacion.MIXED)
        )
        await session.commit()

    await fijar_conversacion_activa(telegram_id, conversacion_id)

    texto_tg = (
        f"<b>Continuacion desde la app</b>\n\n"
        f"Hilo: <b>{conv.titulo}</b>\n\n"
        f"{resumen}\n\n"
        "Puedes seguir aqui; el coach ya tiene este contexto."
    )

    await guardar_mensaje(
        conversacion_id,
        RolMensajeChat.SYSTEM,
        resumen,
        CanalConversacion.SYSTEM,
        metadata={"handoff": "app_to_telegram"},
    )

    session = SafeRedisSession.from_url(
        session_key_for_conversacion(conversacion_id),
        url=settings.redis_url_str,
        ttl=settings.session_ttl_seconds,
    )
    try:
        await session.add_items(
            [
                {
                    "role": "system",
                    "content": f"Contexto handoff desde app Android:\n{resumen}",
                }
            ]
        )
    except Exception:
        logger.exception("No pude inyectar handoff en Redis conv=%s", conversacion_id)
    finally:
        await session.close()

    if bot and telegram_id > 0:
        try:
            await bot.send_message(chat_id=telegram_id, text=texto_tg, parse_mode="HTML")
        except Exception:
            logger.exception("No pude enviar handoff a telegram_id=%s", telegram_id)

    return {"ok": True, "resumen": resumen, "conversacion_id": conversacion_id}
