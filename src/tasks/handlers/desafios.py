"""Handlers Redis: desafíos diarios."""
from __future__ import annotations

import logging
from datetime import date

from telegram.constants import ParseMode

logger = logging.getLogger(__name__)


async def handle_generar(bot, doc: dict) -> None:
    from sqlalchemy import select

    from src.db.connection import async_session_factory
    from src.db.models import Usuario
    from src.services.desafios.generador import generar_desafios_del_dia
    from src.tasks.scheduling import schedule_desafio_aviso_usuario, schedule_desafio_cierre

    payload = doc.get("payload") or {}
    fecha_str = payload.get("fecha")
    fecha = date.fromisoformat(fecha_str) if fecha_str else date.today()
    desafios = await generar_desafios_del_dia(fecha)
    for des in desafios:
        await schedule_desafio_cierre(des.id, des.fecha_fin)
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario.telegram_id).where(
                Usuario.desafios_opt_in == True,  # noqa: E712
                Usuario.onboarding_completo == True,  # noqa: E712
            )
        )
        uids = [int(r[0]) for r in result.all()]
    for uid in uids:
        await schedule_desafio_aviso_usuario(uid, fecha)


async def handle_aviso(bot, doc: dict) -> None:
    from src.services.comunidad import estado_desafio_usuario, usuario_tiene_opt_in
    from src.services.proactive_limit import puede_enviar_proactivo, registrar_envio_proactivo

    telegram_id = int(doc.get("telegram_id") or 0)
    if not telegram_id:
        return
    if not await usuario_tiene_opt_in(telegram_id):
        return
    if not await puede_enviar_proactivo(telegram_id):
        return

    estado = await estado_desafio_usuario(telegram_id)
    if estado is None or not estado["inscrito"]:
        return
    des = estado["desafio"]
    part = estado["participante"]
    valor = part.valor_actual if part else 0
    meta = des.meta_valor
    texto = (
        f"<b>Desafío de hoy</b>\n"
        f"{des.titulo}\n\n"
        f"Progreso: <b>{valor:.0f}</b> / {meta:.0f} ({des.metrica.replace('_', ' ')})\n"
        f"Usa /ranking para ver tu posición."
    )
    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=texto,
            parse_mode=ParseMode.HTML,
            disable_notification=False,
        )
        await registrar_envio_proactivo(telegram_id)
    except Exception:
        logger.exception("Error enviando aviso desafio uid=%s", telegram_id)


async def handle_cierre(bot, doc: dict) -> None:
    from src.services.desafios.premios import cerrar_desafio_y_premiar

    payload = doc.get("payload") or {}
    desafio_id = int(payload.get("desafio_id") or 0)
    if not desafio_id:
        return
    resumen = await cerrar_desafio_y_premiar(desafio_id)
    for prem in resumen.get("premios", []):
        msg = prem.get("mensaje")
        tid = prem.get("telegram_id")
        if msg and tid:
            try:
                await bot.send_message(
                    chat_id=int(tid),
                    text=msg,
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                logger.exception("Error notificando premio desafio uid=%s", tid)
