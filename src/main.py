"""FastAPI + webhook de Telegram. Modo produccion (Railway)."""
from __future__ import annotations

import asyncio
import hmac
import html
import json
import logging
import traceback
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, Defaults

from src.cache import close_redis, ping as ping_redis
from src.config import settings
from src.db.connection import close_db, engine, init_db, ping as ping_db
from src.telegram.bot_setup import setup_bot
from src.telegram.handlers import registrar
from src.telegram.pubsub_listener import start_pubsub_listener
from src.telegram.scheduler import registrar_jobs

logger = logging.getLogger(__name__)

WEBHOOK_SECRET: str = settings.webhook_secret.get_secret_value()
ADMIN_TOKEN: str = settings.admin_token.get_secret_value()

telegram_app: Application | None = None
pubsub_task: asyncio.Task | None = None


async def error_handler(update, context) -> None:
    """Captura excepciones no atrapadas y notifica al developer."""
    logger.error("Excepcion en handler de Telegram", exc_info=context.error)
    if settings.developer_chat_id is None:
        return
    tb = "".join(
        traceback.format_exception(
            None, context.error, context.error.__traceback__
        )
    )
    msg = (
        f"<b>Excepcion en el bot</b>\n"
        f"<pre>{html.escape(str(update))[:1000]}</pre>\n"
        f"<pre>{html.escape(tb)[:2500]}</pre>"
    )
    try:
        await context.bot.send_message(
            chat_id=settings.developer_chat_id, text=msg, parse_mode=ParseMode.HTML
        )
    except Exception:
        logger.exception("No pude notificar al developer")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app, pubsub_task

    await init_db()
    logger.info("Base de datos inicializada")

    defaults = Defaults(
        parse_mode=ParseMode.HTML,
        tzinfo=ZoneInfo(settings.default_timezone),
        disable_notification=False,
    )
    telegram_app = (
        Application.builder()
        .token(settings.telegram_token.get_secret_value())
        .defaults(defaults)
        .post_init(setup_bot)
        .build()
    )
    registrar(telegram_app)
    registrar_jobs(telegram_app)
    telegram_app.add_error_handler(error_handler)

    await telegram_app.initialize()
    await telegram_app.start()
    pubsub_task = start_pubsub_listener(telegram_app)
    logger.info("Telegram app inicializada + pubsub listener activo")

    yield

    if pubsub_task and not pubsub_task.done():
        pubsub_task.cancel()
        try:
            await pubsub_task
        except (asyncio.CancelledError, Exception):
            pass
    if telegram_app:
        try:
            await telegram_app.stop()
            await telegram_app.shutdown()
        except Exception:
            logger.exception("Error apagando telegram_app")
    await close_db()
    await close_redis()


app = FastAPI(title="EntrenadorAX", lifespan=lifespan)

allowed_origins = [
    str(settings.miniapp_url).rstrip("/") if settings.miniapp_url else "*",
    str(settings.admin_url).rstrip("/") if settings.admin_url else "",
    str(settings.landing_url).rstrip("/") if settings.landing_url else "",
]
allowed_origins = [o for o in allowed_origins if o]
if not allowed_origins:
    allowed_origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from src.api.admin import router as admin_router  # noqa: E402
from src.api.auth import router as auth_router  # noqa: E402
from src.api.integraciones import router as integraciones_router  # noqa: E402
from src.api.me import router as me_router  # noqa: E402
from src.api.public import router as public_router  # noqa: E402

app.include_router(auth_router)
app.include_router(me_router)
app.include_router(admin_router)
app.include_router(public_router)
app.include_router(integraciones_router)


@app.get("/health")
async def health() -> dict:
    bot_ok = telegram_app is not None and telegram_app.running
    db_ok = await ping_db()
    redis_ok = await ping_redis()
    status_ok = bot_ok and db_ok and redis_ok
    pool_info = {}
    try:
        pool_info = {
            "size": engine.pool.size(),
            "checked_out": engine.pool.checkedout(),
            "overflow": engine.pool.overflow(),
        }
    except Exception:
        pass
    return {
        "status": "ok" if status_ok else "degraded",
        "bot": bot_ok,
        "db": db_ok,
        "redis": redis_ok,
        "db_pool": pool_info,
    }


@app.post("/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None),
):
    if telegram_app is None or not telegram_app.running:
        raise HTTPException(503, "Bot no listo")

    if not hmac.compare_digest(
        x_telegram_bot_api_secret_token or "", WEBHOOK_SECRET
    ):
        raise HTTPException(403, "Token invalido")

    body = await request.body()
    if len(body) > settings.max_webhook_payload_bytes:
        raise HTTPException(413, "Payload too large")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(400, "JSON invalido")

    update = Update.de_json(data, telegram_app.bot)
    if update is None:
        return {"ok": True}
    await telegram_app.process_update(update)
    return {"ok": True}


@app.get("/webhook-info")
async def webhook_info(x_admin_token: str = Header(None)) -> dict:
    """Devuelve la URL de webhook y secret. Protegido por X-Admin-Token."""
    if not hmac.compare_digest(x_admin_token or "", ADMIN_TOKEN):
        raise HTTPException(403, "Acceso denegado")
    base = str(settings.webhook_base_url).rstrip("/") if settings.webhook_base_url else ""
    return {
        "webhook_url": f"{base}/webhook" if base else None,
        "secret_token": WEBHOOK_SECRET,
        "note": (
            "curl -X POST 'https://api.telegram.org/bot<TOKEN>/setWebhook?"
            "url=<webhook_url>&secret_token=<secret_token>'"
        ),
    }


@app.get("/admin/stats")
async def admin_stats(x_admin_token: str = Header(None)) -> dict:
    """Estadisticas basicas. Protegido por X-Admin-Token."""
    from datetime import date as date_t
    from datetime import timedelta

    from sqlalchemy import func, select

    from src.db.connection import async_session_factory
    from src.db.models import (
        CrisisLog,
        EventoBot,
        Suscripcion,
        Usuario,
    )

    if not hmac.compare_digest(x_admin_token or "", ADMIN_TOKEN):
        raise HTTPException(403, "Acceso denegado")
    hoy = date_t.today()
    hace_30 = hoy - timedelta(days=30)
    async with async_session_factory() as session:
        total_users = (
            await session.execute(select(func.count(Usuario.id)))
        ).scalar() or 0
        onboarded = (
            await session.execute(
                select(func.count(Usuario.id)).where(
                    Usuario.onboarding_completo == True  # noqa: E712
                )
            )
        ).scalar() or 0
        bloqueados = (
            await session.execute(
                select(func.count(Usuario.id)).where(
                    Usuario.bot_bloqueado == True  # noqa: E712
                )
            )
        ).scalar() or 0
        pro_activos = (
            await session.execute(
                select(func.count(Suscripcion.id)).where(
                    Suscripcion.activa == True,  # noqa: E712
                )
            )
        ).scalar() or 0
        eventos_30d = (
            await session.execute(
                select(EventoBot.tipo_evento, func.count(EventoBot.id))
                .where(EventoBot.creado_en >= hace_30)
                .group_by(EventoBot.tipo_evento)
            )
        ).all()
        crisis_30d = (
            await session.execute(
                select(CrisisLog.nivel, func.count(CrisisLog.id))
                .where(CrisisLog.creado_en >= hace_30)
                .group_by(CrisisLog.nivel)
            )
        ).all()
    return {
        "fecha": hoy.isoformat(),
        "usuarios": {
            "total": total_users,
            "onboarded": onboarded,
            "bloqueados": bloqueados,
            "pro_activos": pro_activos,
        },
        "eventos_30d": {tipo: cnt for tipo, cnt in eventos_30d},
        "crisis_30d_por_nivel": {nivel: cnt for nivel, cnt in crisis_30d},
    }
