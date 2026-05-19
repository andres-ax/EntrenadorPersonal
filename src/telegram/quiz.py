"""Polls de Telegram: check-in nocturno + quiz educativo semanal."""

from __future__ import annotations

import logging
import random

from src.db.repository import (guardar_checkin_nocturno,
                               listar_usuarios_activos, log_evento)
from telegram import Poll, Update
from telegram.constants import ParseMode
from telegram.ext import Application, ContextTypes, PollAnswerHandler

logger = logging.getLogger(__name__)


CHECKIN_OPCIONES = [
    "Entrene + comi bien + dormi bien",
    "Hice 2 de 3",
    "Solo 1 de 3",
    "Dia perdido",
]


QUIZ_EDUCATIVO = [
    {
        "q": "Cuantos gramos de proteina/kg recomienda ISSN para hipertrofia?",
        "options": ["0.8-1.2", "1.2-1.4", "1.6-2.2", "3.0-4.0"],
        "correct": 2,
        "explanation": "ISSN 2017: 1.6-2.2 g/kg para hipertrofia. (Jager et al, JISSN)",
    },
    {
        "q": "Cuantas series semanales por musculo recomienda ACSM 2026?",
        "options": ["3-5", "10+ (con diminishing returns)", "30+", "Sin recomendacion"],
        "correct": 1,
        "explanation": "ACSM 2026 Position Stand: >=10 sets/musculo/semana es optimo.",
    },
    {
        "q": "Para mejorar hipertrofia, el RIR optimo en working sets es:",
        "options": ["RIR 0 (siempre al fallo)", "RIR 1-3", "RIR 5-7", "No importa"],
        "correct": 1,
        "explanation": "Grgic 2022 meta-analisis: RIR 0-3 produce hipertrofia equivalente, pero RIR 1-3 con compuestos es mas sostenible.",
    },
    {
        "q": "AASM recomienda para adultos sanos:",
        "options": ["4-6 h", "7-9 h", "10-12 h", "Variable"],
        "correct": 1,
        "explanation": "AASM/NSF 2015: 7-9 horas para adultos sanos.",
    },
    {
        "q": "El deficit calorico optimo para perder grasa sin perder musculo es:",
        "options": ["5% de TDEE", "10-20% de TDEE", "30%+ de TDEE", "Ayuno total"],
        "correct": 1,
        "explanation": "Helms et al 2014 JISSN: 10-20% TDEE es sweet spot. >25% TDEE = riesgo perdida muscular.",
    },
]


async def quiz_nocturno(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job 21:30 local: envia poll de check-in. PollAnswerHandler lo registra."""
    try:
        usuarios = await listar_usuarios_activos()
        for u in usuarios:
            try:
                await context.bot.send_poll(
                    chat_id=u.telegram_id,
                    question="Check-in nocturno: como fue tu dia?",
                    options=CHECKIN_OPCIONES,
                    is_anonymous=False,
                    allows_multiple_answers=False,
                    disable_notification=True,
                )
            except Exception:
                logger.warning("No pude enviar quiz a %s", u.telegram_id)
    except Exception:
        logger.exception("Error en quiz_nocturno")


async def quiz_educativo_semanal(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job sabado 10am: envia 1 quiz educativo random."""
    try:
        usuarios = await listar_usuarios_activos()
        q = random.choice(QUIZ_EDUCATIVO)
        for u in usuarios:
            try:
                await context.bot.send_poll(
                    chat_id=u.telegram_id,
                    question=q["q"],
                    options=q["options"],
                    type=Poll.QUIZ,
                    correct_option_id=q["correct"],
                    explanation=q["explanation"],
                    is_anonymous=False,
                )
            except Exception:
                logger.warning("No pude enviar quiz edu a %s", u.telegram_id)
    except Exception:
        logger.exception("Error en quiz_educativo_semanal")


async def manejar_poll_answer(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """PollAnswerHandler: registra respuesta del checkin nocturno."""
    ans = update.poll_answer
    if not ans or not ans.option_ids:
        return
    uid = ans.user.id
    opcion = ans.option_ids[0]
    try:
        await guardar_checkin_nocturno(uid, opcion, via="poll")
        await log_evento(uid, "checkin_poll", {"opcion": opcion})
        feedback = {
            0: "<b>Crack.</b> Tres de tres. Sigue asi.",
            1: "<b>Bien.</b> Manana vamos por el tercero.",
            2: "Algo es algo. Manana subimos.",
            3: "Dia rough. Manana reseteamos. Aqui estoy.",
        }.get(opcion, "Anotado.")
        await ctx.bot.send_message(
            chat_id=uid, text=feedback, parse_mode=ParseMode.HTML
        )
    except Exception:
        logger.exception("Error procesando poll answer uid=%s", uid)


def registrar_handlers_quiz(app: Application) -> None:
    app.add_handler(PollAnswerHandler(manejar_poll_answer))
