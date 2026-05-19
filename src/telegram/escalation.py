"""Sistema de escalation: el coach que NO te deja en paz cuando fallas.

Algoritmo basado en research/tough-love-coaching-framework.md seccion 3.

- 5 niveles (0=ok, 1=suave, 2=recordatorio, 3=presion, 4=urgencia ultima).
- 3 tonos (amigable, firme, militar).
- 4 tipos de accion (entreno, comida, sueno, peso).
- Cooldown 4h entre mensajes nivel >=3.
- Techo absoluto 4 mensajes/dia.
- Hard-enforce quiet hours (re-schedule a fin+30min).
- Honoring pausado_hasta y bot_bloqueado.
- Auto-cancel cuando el usuario cumple.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

import telegram.error
from src.db.connection import async_session_factory
from src.db.models import (Comida, MetricaCorporal, MetricaSueno,
                           SesionEntrenamiento, TonoCoach, Usuario)
from src.db.repository import (avanzar_escalacion, listar_usuarios_activos,
                               log_evento, marcar_bot_bloqueado,
                               obtener_o_crear_escalacion, reset_escalacion)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

OFFSET_POR_LEVEL = {1: 6, 2: 5, 3: 2}
MAX_LEVEL = 4
COOLDOWN_HARD_HOURS = 4
MAX_MENSAJES_DIA = 4


ESCALADO_COPY_EN: dict[str, dict[str, list[str]]] = {
    "entreno": {
        "amigable": [
            "",
            "Hi {nombre}, training day per your plan. <i>How are you feeling?</i>",
            "{nombre}, afternoon's here. If not today, when? Drop me a line.",
            "It's been days without a log. <b>Are you ok?</b> If you need a break, /pausa.",
            "{nombre}, I care. Your commitment needs you. If not today, tomorrow we start fresh together.",
        ],
        "firme": [
            "",
            "{nombre}, training today. <b>Confirm when done.</b>",
            "{nombre}, half the day gone. <b>Haven't trained yet?</b>",
            "<b>{nombre}, real talk.</b> {dias} days in a row without training. Your commitment says {freq} days/week. <b>What's up?</b>",
            "Last one today, {nombre}. If you don't train you <b>break</b> the {streak}-day streak.",
        ],
        "militar": [
            "",
            "{nombre}. <b>Training today.</b> 7am tomorrow confirm.",
            "{nombre}. <b>Noon.</b> No movement yet. Report.",
            "<b>{nombre}. {dias} DAYS.</b> Commitment broken. <b>Today. No excuses.</b>",
            "{nombre}. Final warning. Tomorrow 7am you train. <b>Confirm or I stop.</b>",
        ],
    },
    "comida": {
        "amigable": [
            "",
            "Hi {nombre}, how's nutrition going today? <i>What did you eat?</i>",
            "{nombre}, haven't seen meal logs. Happy to help with macros.",
            "Day's almost over and I don't know what you ate, {nombre}. Tell me so I can support you.",
            "{nombre}, no nutrition = no results. Tomorrow we start with breakfast tracked, ok?",
        ],
        "firme": [
            "",
            "{nombre}, no food logged today. <b>What have you had?</b>",
            "{nombre}, {dias} days without meal logs. <b>Goal is {objetivo}.</b> No tracking, no control.",
            "{dias} days no nutrition tracked, {nombre}. Your commitment demands consistency.",
            "Last one, {nombre}. Tomorrow you start tracking breakfast. <b>Confirm.</b>",
        ],
        "militar": [
            "",
            "{nombre}. <b>Today's meals.</b> Report.",
            "{nombre}. <b>{dias} days no tracking.</b> Unacceptable for your goal {objetivo}.",
            "<b>{nombre}. Zero nutrition logged.</b> Your commitment demands it. Today you report or you report.",
            "Final nutrition warning, {nombre}. Tomorrow breakfast tracked. <b>Confirm.</b>",
        ],
    },
    "sueno": {
        "amigable": [
            "",
            "Good morning {nombre}! <i>How did you sleep?</i> Hours and quality 1-5.",
            "{nombre}, I don't know how you slept. No sleep = stalled progress. Tell me.",
            "{dias} days no sleep logged, {nombre}. Recovery is training too.",
            "{nombre}, without sleep tracked I can't tell if you're recovering. Tomorrow we start, ok?",
        ],
        "firme": [
            "",
            "{nombre}, how many hours and quality (1-5)?",
            "{nombre}, {dias} days no sleep logs. <b>It's 30% of your progress.</b>",
            "{dias} days no sleep tracked, {nombre}. Without recovery, no supercompensation.",
            "Tomorrow on wake, {nombre}, first message: <b>hours and quality</b>. No excuses.",
        ],
        "militar": [
            "",
            "{nombre}. <b>Last night's sleep?</b> Hours and quality 1-5.",
            "{nombre}. <b>{dias} days no sleep reported.</b> Your physiology depends on it.",
            "<b>{nombre}. Sleep = recovery = progress.</b> No report no plan.",
            "Tomorrow 8am report sleep, {nombre}. <b>Confirm.</b>",
        ],
    },
    "peso": {
        "amigable": [
            "",
            "{nombre}, {dias} days without weighing in. <i>How's it going?</i>",
            "Almost 2 weeks no weight logged, {nombre}. Without data I can't tell.",
            "{nombre}, no weighing means no progress visible. Which day works best weekly?",
            "{nombre}, weigh tomorrow fasted. No pressure. It's your baseline for {objetivo}.",
        ],
        "firme": [
            "",
            "{nombre}, {dias} days no weight. <b>Weigh tomorrow fasted.</b>",
            "{nombre}, no weekly weight means I can't verify your plan works. Tomorrow, scale.",
            "<b>{dias} days no weight, {nombre}.</b> Your commitment requires tracking. Today or tomorrow.",
            "Final weight warning, {nombre}. Tomorrow fasted or Monday <b>mandatory</b>.",
        ],
        "militar": [
            "",
            "{nombre}. <b>Weekly weigh-in.</b> Tomorrow fasted report.",
            "{nombre}. <b>{dias} days no weight.</b> Unacceptable for serious tracking.",
            "<b>{nombre}. No weight = no data = no plan.</b> Tomorrow scale. No excuses.",
            "Final weight warning, {nombre}. Tomorrow or Monday you report. <b>Confirm.</b>",
        ],
    },
}


ESCALADO_COPY_PT: dict[str, dict[str, list[str]]] = {
    "entreno": {
        "amigable": [
            "",
            "Oi {nombre}, hoje e dia de treino segundo seu plano. <i>Como esta se sentindo?</i>",
            "{nombre}, ja e tarde. Se nao for hoje, quando? Me manda uma mensagem.",
            "Faz dias sem registro. <b>Esta bem?</b> Se precisa de pausa, /pausa.",
            "{nombre}, te quero bem. Seu compromisso precisa de voce. Se hoje nao, amanha comecamos juntos.",
        ],
        "firme": [
            "",
            "{nombre}, treino hoje. <b>Confirma quando terminar.</b>",
            "{nombre}, meio-dia ja. <b>Ainda nao treinou?</b>",
            "<b>{nombre}, vamos falar serio.</b> {dias} dias seguidos sem treinar. Seu compromisso diz {freq} dias por semana. <b>O que houve?</b>",
            "Ultima do dia, {nombre}. Se nao treinar hoje <b>quebra</b> a sequencia de {streak} dias.",
        ],
        "militar": [
            "",
            "{nombre}. <b>Treino hoje.</b> 7h da manha confirma.",
            "{nombre}. <b>Meio-dia.</b> Sem movimento ainda. Reporte.",
            "<b>{nombre}. {dias} DIAS.</b> Compromisso quebrado. <b>Hoje. Sem desculpas.</b>",
            "{nombre}. Ultimo aviso. Amanha 7h voce treina. <b>Confirma ou paro.</b>",
        ],
    },
    "comida": {
        "amigable": [
            "",
            "Oi {nombre}, como vai a nutricao hoje? <i>O que comeu?</i>",
            "{nombre}, nao vi registros de comida. Te ajudo com macros se quiser.",
            "O dia ta acabando e nao sei o que voce comeu, {nombre}. Me conta.",
            "{nombre}, sem nutricao nao tem resultados. Amanha comecamos pelo cafe da manha tracked, ta?",
        ],
        "firme": [
            "",
            "{nombre}, sem comida registrada hoje. <b>O que comeu?</b>",
            "{nombre}, {dias} dias sem registros de comida. <b>Objetivo: {objetivo}.</b> Sem tracking nao tem controle.",
            "{dias} dias sem nutricao registrada, {nombre}. Seu compromisso pede consistencia.",
            "Ultima, {nombre}. Amanha voce comeca tracking do cafe. <b>Confirma.</b>",
        ],
        "militar": [
            "",
            "{nombre}. <b>Refeicoes do dia.</b> Reporte.",
            "{nombre}. <b>{dias} dias sem tracking.</b> Inaceitavel para {objetivo}.",
            "<b>{nombre}. Zero registro de nutricao.</b> Seu compromisso exige. Hoje voce reporta ou reporta.",
            "Ultimo aviso nutricao, {nombre}. Amanha cafe tracked. <b>Confirma.</b>",
        ],
    },
    "sueno": {
        "amigable": [
            "",
            "Bom dia {nombre}! <i>Como dormiu?</i> Horas e qualidade 1-5.",
            "{nombre}, nao sei como dormiu. Sem sono seu progresso trava. Me conta.",
            "{dias} dias sem registro de sono, {nombre}. Recuperacao tambem e treino.",
            "{nombre}, sem sono tracked nao entendo se voce se recupera. Amanha comecamos, ta?",
        ],
        "firme": [
            "",
            "{nombre}, quantas horas dormiu e qualidade (1-5)?",
            "{nombre}, {dias} dias sem registrar sono. <b>E 30% do seu progresso.</b>",
            "{dias} dias sem sono tracked, {nombre}. Sem recuperacao nao tem supercompensacao.",
            "Amanha ao acordar, {nombre}, primeira mensagem: <b>horas e qualidade</b>. Sem desculpas.",
        ],
        "militar": [
            "",
            "{nombre}. <b>Sono de ontem?</b> Horas e qualidade 1-5.",
            "{nombre}. <b>{dias} dias sem sono reportado.</b> Sua fisiologia depende disso.",
            "<b>{nombre}. Sono = recuperacao = progresso.</b> Sem reporte sem plano.",
            "Amanha 8h reporta sono, {nombre}. <b>Confirma.</b>",
        ],
    },
    "peso": {
        "amigable": [
            "",
            "{nombre}, {dias} dias sem se pesar. <i>Como vai?</i>",
            "Quase 2 semanas sem peso registrado, {nombre}. Sem dados nao consigo te acompanhar.",
            "{nombre}, sem se pesar nao vejo seu progresso. Que dia te serve melhor pra fazer semanal?",
            "{nombre}, se pese amanha em jejum. Sem pressao. E sua base pro objetivo {objetivo}.",
        ],
        "firme": [
            "",
            "{nombre}, {dias} dias sem se pesar. <b>Se pese amanha em jejum.</b>",
            "{nombre}, sem peso semanal nao sei se funciona seu plano. Amanha, balanca.",
            "<b>{dias} dias sem peso, {nombre}.</b> Seu compromisso pede tracking. Hoje ou amanha.",
            "Ultima do peso, {nombre}. Amanha em jejum ou segunda <b>obrigatorio</b>.",
        ],
        "militar": [
            "",
            "{nombre}. <b>Peso semanal.</b> Amanha em jejum reporte.",
            "{nombre}. <b>{dias} dias sem peso.</b> Inaceitavel para tracking serio.",
            "<b>{nombre}. Sem peso = sem dados = sem plano.</b> Amanha balanca. Sem desculpas.",
            "Ultimo aviso peso, {nombre}. Amanha ou segunda voce reporta. <b>Confirma.</b>",
        ],
    },
}


ESCALADO_COPY: dict[str, dict[str, list[str]]] = {
    "entreno": {
        "amigable": [
            "",
            "Hola {nombre}, hoy toca entrenar segun tu plan. <i>Como te sientes?</i>",
            "{nombre}, ya va la tarde. Si no es hoy, cuando? Mandame un mensajito.",
            "Hace ya unos dias sin registro. <b>Estas bien?</b> Si necesitas pausa, /pausa.",
            "{nombre}, te quiero. Tu compromiso te necesita. Si hoy no, manana arrancamos juntos.",
        ],
        "firme": [
            "",
            "{nombre}, hoy toca entrenar. <b>Confirma cuando termines.</b>",
            "{nombre}, ya paso medio dia. <b>Aun no entrenas?</b>",
            "<b>{nombre}, hablemos claro.</b> Llevas {dias} dias seguidos sin entrenar. Tu compromiso dice {freq} dias por semana. <b>Que pasa?</b>",
            "Ultima del dia, {nombre}. Si no entrenas hoy <b>rompes</b> la racha de {streak} dias.",
        ],
        "militar": [
            "",
            "{nombre}. <b>Entreno hoy.</b> 7:00 manana confirma.",
            "{nombre}. <b>Mediodia.</b> Sin movimiento aun. Reporta.",
            "<b>{nombre}. {dias} DIAS.</b> Compromiso roto. <b>Hoy. Sin excusas.</b>",
            "{nombre}. Ultimo aviso. Manana 7:00 entrenas. <b>Confirma o paro de molestarte.</b>",
        ],
    },
    "comida": {
        "amigable": [
            "",
            "Hola {nombre}, como va con la nutricion hoy? <i>Que comiste?</i>",
            "{nombre}, no he visto que registres comidas. Te ayudo con macros si quieres.",
            "Ya casi termina el dia y no se que comiste, {nombre}. Cuentame para acompanarte.",
            "{nombre}, sin nutricion no hay resultados. Manana arrancamos con desayuno tracked, va?",
        ],
        "firme": [
            "",
            "{nombre}, no has registrado nada de comida hoy. <b>Que llevas?</b>",
            "{nombre}, llevas {dias} dias sin registrar comidas. <b>Tu objetivo es {objetivo}.</b> Sin tracking no hay control.",
            "{dias} dias sin nutricion registrada, {nombre}. Tu compromiso pide consistencia.",
            "Ultima, {nombre}. Manana arrancas tracking del desayuno. <b>Confirma.</b>",
        ],
        "militar": [
            "",
            "{nombre}. <b>Comidas del dia.</b> Reporta.",
            "{nombre}. <b>{dias} dias sin tracking.</b> Inaceptable para tu objetivo {objetivo}.",
            "<b>{nombre}. Cero registro de nutricion.</b> Tu compromiso lo exige. Hoy reportas o reportas.",
            "Ultimo aviso nutricion, {nombre}. Manana desayuno tracked. <b>Confirma.</b>",
        ],
    },
    "sueno": {
        "amigable": [
            "",
            "Buen dia {nombre}! <i>Como dormiste?</i> Cuentame horas y calidad 1-5.",
            "{nombre}, no se como dormiste. Sin sueno tu progreso se frena. Cuentame.",
            "Ya van {dias} dias sin registro de sueno, {nombre}. La recuperacion es entreno tambien.",
            "{nombre}, sin sueno tracked no entiendo si te recuperas. Manana arrancamos, va?",
        ],
        "firme": [
            "",
            "{nombre}, cuantas horas dormiste y que tal (1-5)?",
            "{nombre}, llevas {dias} dias sin registrar sueno. <b>Es 30% de tu progreso.</b>",
            "{dias} dias sin sueno tracked, {nombre}. Sin recuperacion no hay supercompensacion.",
            "Manana al despertar, {nombre}, primer mensaje: <b>horas y calidad</b>. Sin excusas.",
        ],
        "militar": [
            "",
            "{nombre}. <b>Sueno de anoche?</b> Horas y calidad 1-5.",
            "{nombre}. <b>{dias} dias sin sueno reportado.</b> Tu fisiologia depende de eso.",
            "<b>{nombre}. Sueno = recuperacion = progreso.</b> Sin reporte no hay plan.",
            "Manana 8:00 reportas sueno, {nombre}. <b>Confirma.</b>",
        ],
    },
    "peso": {
        "amigable": [
            "",
            "{nombre}, llevas {dias} dias sin pesarte. <i>Como vas?</i>",
            "Hace casi 2 semanas sin peso registrado, {nombre}. Sin datos no se como vamos.",
            "{nombre}, sin pesarte no veo tu progreso. Que dia te queda mejor para hacerlo semanal?",
            "{nombre}, pesate manana en ayunas. Sin presion. Es el dato base de tu objetivo {objetivo}.",
        ],
        "firme": [
            "",
            "{nombre}, llevas {dias} dias sin pesarte. <b>Pesate manana en ayunas.</b>",
            "{nombre}, sin peso semanal no se si funciona tu plan. Manana, balanza.",
            "<b>{dias} dias sin peso, {nombre}.</b> Tu compromiso pide tracking. Hoy o manana.",
            "Ultima del peso, {nombre}. Manana en ayunas o el lunes <b>obligatorio</b>.",
        ],
        "militar": [
            "",
            "{nombre}. <b>Peso semanal.</b> Manana en ayunas reporta.",
            "{nombre}. <b>{dias} dias sin peso.</b> Inaceptable para tracking serio.",
            "<b>{nombre}. Sin peso = sin datos = sin plan.</b> Manana balanza. Sin excusas.",
            "Ultimo aviso peso, {nombre}. Manana o lunes reportas. <b>Confirma.</b>",
        ],
    },
}


async def _en_quiet_hours(usuario: Usuario, ahora: datetime | None = None) -> bool:
    ahora = ahora or datetime.now(ZoneInfo(usuario.timezone or "America/Bogota"))
    hora_actual = ahora.time()
    inicio = usuario.quiet_hours_inicio or time(22, 0)
    fin = usuario.quiet_hours_fin or time(7, 0)
    if inicio > fin:
        return hora_actual >= inicio or hora_actual < fin
    return inicio <= hora_actual < fin


def _proximo_envio_post_quiet(usuario: Usuario) -> datetime:
    tz = ZoneInfo(usuario.timezone or "America/Bogota")
    ahora = datetime.now(tz)
    fin = usuario.quiet_hours_fin or time(7, 0)
    proximo = ahora.replace(hour=fin.hour, minute=fin.minute, second=0, microsecond=0)
    if proximo <= ahora:
        proximo += timedelta(days=1)
    return proximo + timedelta(minutes=30)


async def _esta_pausado(usuario: Usuario) -> bool:
    return usuario.pausado_hasta is not None and usuario.pausado_hasta >= date.today()


async def _ya_cumplio_hoy(usuario_id: int, tipo_accion: str) -> bool:
    """Chequea si ya hay registro de hoy del tipo de accion."""
    hoy = date.today()
    async with async_session_factory() as session:
        if tipo_accion == "entreno":
            query = select(func.count(SesionEntrenamiento.id)).where(
                SesionEntrenamiento.usuario_id == usuario_id,
                SesionEntrenamiento.fecha == hoy,
            )
        elif tipo_accion == "comida":
            query = select(func.count(Comida.id)).where(
                Comida.usuario_id == usuario_id,
                Comida.fecha == hoy,
            )
        elif tipo_accion == "sueno":
            query = select(func.count(MetricaSueno.id)).where(
                MetricaSueno.usuario_id == usuario_id,
                MetricaSueno.fecha == hoy,
            )
        elif tipo_accion == "peso":
            inicio = hoy - timedelta(days=7)
            query = select(func.count(MetricaCorporal.id)).where(
                MetricaCorporal.usuario_id == usuario_id,
                MetricaCorporal.fecha >= inicio,
            )
        else:
            return False
        result = await session.execute(query)
        return (result.scalar() or 0) > 0


async def _dias_consecutivos_sin(usuario_id: int, tipo_accion: str) -> int:
    """Aprox: distancia en dias desde el ultimo registro de ese tipo."""
    async with async_session_factory() as session:
        if tipo_accion == "entreno":
            query = select(func.max(SesionEntrenamiento.fecha)).where(
                SesionEntrenamiento.usuario_id == usuario_id
            )
        elif tipo_accion == "comida":
            query = select(func.max(Comida.fecha)).where(
                Comida.usuario_id == usuario_id
            )
        elif tipo_accion == "sueno":
            query = select(func.max(MetricaSueno.fecha)).where(
                MetricaSueno.usuario_id == usuario_id
            )
        elif tipo_accion == "peso":
            query = select(func.max(MetricaCorporal.fecha)).where(
                MetricaCorporal.usuario_id == usuario_id
            )
        else:
            return 0
        result = await session.execute(query)
        ultima = result.scalar()
        if ultima is None:
            return 999
        return (date.today() - ultima).days


_COPY_POR_LANG: dict[str, dict[str, dict[str, list[str]]]] = {
    "es": ESCALADO_COPY,
    "en": ESCALADO_COPY_EN,
    "pt": ESCALADO_COPY_PT,
}


def _formatear_copy(
    nombre: str | None,
    tono: str,
    tipo_accion: str,
    level: int,
    dias: int,
    streak: int = 0,
    objetivo: str = "tu objetivo",
    freq: int = 3,
    lang: str = "es",
    pais: str | None = None,
) -> str:
    """Resuelve el template para (level, tono, tipo_accion, lang) y aplica jerga regional."""
    fuente = _COPY_POR_LANG.get(lang, ESCALADO_COPY)
    plantillas = fuente.get(tipo_accion, {}).get(tono)
    if not plantillas:
        plantillas = (
            fuente.get(tipo_accion, {}).get("firme")
            or ESCALADO_COPY[tipo_accion]["firme"]
        )
    level = max(0, min(level, MAX_LEVEL))
    template = plantillas[level] if level < len(plantillas) else plantillas[-1]
    texto = template.format(
        nombre=nombre or "crack",
        dias=max(1, dias),
        streak=streak,
        objetivo=objetivo,
        freq=freq,
    )
    if pais and tono != "militar":
        from src.i18n import aplicar_jerga

        texto = aplicar_jerga(texto, pais)
    return texto


async def recordatorio_escalado(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback ejecutado por JobQueue: lee state, decide level, envia y agenda siguiente."""
    data = ctx.job.data or {}
    uid: int = data["uid"]
    tipo_accion: str = data.get("tipo_accion", "entreno")

    async with async_session_factory() as session:
        u = (
            await session.execute(select(Usuario).where(Usuario.telegram_id == uid))
        ).scalar_one_or_none()

    if u is None or u.bot_bloqueado or not u.onboarding_completo:
        return

    if await _esta_pausado(u):
        logger.info("uid=%s pausado, salto escalado", uid)
        return

    if await _ya_cumplio_hoy(u.id, tipo_accion):
        await reset_escalacion(uid, tipo_accion)
        logger.info("uid=%s ya cumplio %s, reset escalado", uid, tipo_accion)
        return

    estado = await obtener_o_crear_escalacion(uid, tipo_accion)

    if estado.mensajes_enviados_hoy >= MAX_MENSAJES_DIA:
        logger.info("uid=%s techo diario %s alcanzado", uid, tipo_accion)
        return

    next_level = min(estado.level + 1, MAX_LEVEL)

    if estado.ultimo_envio is not None and next_level >= 3:
        delta = datetime.utcnow() - estado.ultimo_envio
        if delta < timedelta(hours=COOLDOWN_HARD_HOURS):
            faltan = timedelta(hours=COOLDOWN_HARD_HOURS) - delta
            ctx.job_queue.run_once(
                recordatorio_escalado,
                when=faltan,
                data=data,
                name=f"escalado_{uid}_{tipo_accion}_{next_level}",
            )
            return

    if await _en_quiet_hours(u):
        proximo = _proximo_envio_post_quiet(u)
        ctx.job_queue.run_once(
            recordatorio_escalado,
            when=proximo,
            data=data,
            name=f"escalado_{uid}_{tipo_accion}_{next_level}",
        )
        return

    tono = u.tono.value if u.tono else TonoCoach.FIRME.value
    dias = await _dias_consecutivos_sin(u.id, tipo_accion)
    streak = data.get("streak", 0)
    objetivo = u.objetivo or "tu objetivo"
    freq = data.get("freq", u.dias_entreno or 3)

    texto = _formatear_copy(
        nombre=u.nombre,
        tono=tono,
        tipo_accion=tipo_accion,
        level=next_level,
        dias=dias,
        streak=streak,
        objetivo=objetivo,
        freq=freq,
        lang=(u.idioma or "es"),
        pais=u.pais,
    )

    silent = next_level <= 1
    try:
        if next_level >= 3 and tono in ("firme", "militar"):
            from src.db.repository import es_usuario_pro
            from src.services.tts import enviar_voz

            es_pro = await es_usuario_pro(uid)
            voz_ok = False
            if es_pro:
                voz_ok = await enviar_voz(
                    ctx.bot,
                    uid,
                    texto.replace("<b>", "")
                    .replace("</b>", "")
                    .replace("<i>", "")
                    .replace("</i>", ""),
                    tono=tono,
                )
            if not voz_ok:
                msg = await ctx.bot.send_message(
                    chat_id=uid,
                    text=texto,
                    parse_mode=ParseMode.HTML,
                    disable_notification=silent,
                )
                mensaje_id = msg.message_id
            else:
                mensaje_id = None
        else:
            msg = await ctx.bot.send_message(
                chat_id=uid,
                text=texto,
                parse_mode=ParseMode.HTML,
                disable_notification=silent,
            )
            mensaje_id = msg.message_id
        await avanzar_escalacion(uid, tipo_accion, mensaje_id=mensaje_id)
        await log_evento(
            uid,
            f"escalado_{tipo_accion}",
            {"level": next_level, "tono": tono, "dias": dias},
        )
    except telegram.error.Forbidden:
        await marcar_bot_bloqueado(uid, True)
        logger.info("Bot bloqueado por %s, marcado en DB", uid)
        return
    except telegram.error.RetryAfter as e:
        ctx.job_queue.run_once(
            recordatorio_escalado,
            when=timedelta(seconds=e.retry_after + 1),
            data=data,
            name=f"escalado_{uid}_{tipo_accion}_{next_level}_retry",
        )
        return
    except Exception:
        logger.exception("Error enviando escalado uid=%s", uid)
        return

    if next_level < MAX_LEVEL:
        offset_h = OFFSET_POR_LEVEL.get(next_level, 4)
        ctx.job_queue.run_once(
            recordatorio_escalado,
            when=timedelta(hours=offset_h),
            data=data,
            name=f"escalado_{uid}_{tipo_accion}_{next_level + 1}",
        )


async def disparar_escalado_inicial(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Job 8am: para cada usuario activo, arranca cadena nivel 1 si toca.

    Llamado desde scheduler.recordatorio_entreno como reemplazo del envio directo.
    """
    try:
        usuarios = await listar_usuarios_activos()
    except Exception:
        logger.exception("Error listando usuarios activos para escalado")
        return

    for u in usuarios:
        for tipo in ("entreno", "comida", "sueno"):
            if await _ya_cumplio_hoy(u.id, tipo):
                continue
            existing_name = f"escalado_{u.telegram_id}_{tipo}_1"
            for job in ctx.job_queue.get_jobs_by_name(existing_name):
                job.schedule_removal()
            ctx.job_queue.run_once(
                recordatorio_escalado,
                when=timedelta(seconds=1),
                data={
                    "uid": u.telegram_id,
                    "tipo_accion": tipo,
                    "freq": u.dias_entreno or 3,
                },
                name=f"escalado_{u.telegram_id}_{tipo}_1",
            )


async def cancelar_escalado_hoy(
    uid: int, ctx: ContextTypes.DEFAULT_TYPE, tipo_accion: Optional[str] = None
) -> int:
    """Cancela todos los jobs de escalation de hoy para el usuario.

    Llamado desde el handler cuando el usuario confirma una accion.

    Args:
        uid: telegram_id del usuario.
        ctx: contexto con ctx.job_queue.
        tipo_accion: si None, cancela todos los tipos.

    Returns:
        Numero de jobs cancelados.

    """
    cancelados = 0
    tipos = [tipo_accion] if tipo_accion else ["entreno", "comida", "sueno", "peso"]
    for tipo in tipos:
        for level in range(1, MAX_LEVEL + 1):
            nombre = f"escalado_{uid}_{tipo}_{level}"
            for job in ctx.job_queue.get_jobs_by_name(nombre):
                job.schedule_removal()
                cancelados += 1
    if cancelados:
        await reset_escalacion(uid, tipo_accion)
        logger.info(
            "Cancelados %s jobs de escalado para uid=%s tipo=%s",
            cancelados,
            uid,
            tipo_accion or "all",
        )
    return cancelados
