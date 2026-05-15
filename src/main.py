import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from telegram import Update
from telegram.ext import Application

from src.config import settings
from src.db.connection import close_db, init_db
from src.telegram.handlers import registrar
from src.telegram.middlewares import close_redis

logger = logging.getLogger(__name__)

WEBHOOK_SECRET = secrets.token_hex(32)

telegram_app: Application | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app

    await init_db()
    logger.info("Base de datos inicializada")

    telegram_app = Application.builder().token(settings.telegram_token).build()
    registrar(telegram_app)
    await telegram_app.initialize()
    await telegram_app.start()
    logger.info("Telegram app inicializada y lista")

    yield

    if telegram_app:
        await telegram_app.stop()
        await telegram_app.shutdown()
    await close_db()
    await close_redis()


app = FastAPI(title="EntrenadorAX", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "bot": telegram_app is not None}


@app.post("/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None),
):
    if telegram_app is None:
        raise HTTPException(503, "Bot no inicializado")

    if x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(403, "Token invalido")

    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}


@app.get("/webhook-info")
async def webhook_info():
    """Devuelve el secret para configurar el webhook de Telegram."""
    return {
        "webhook_url": f"{settings.webhook_base_url}/webhook",
        "secret_token": WEBHOOK_SECRET,
        "note": "Usa: curl -X POST 'https://api.telegram.org/bot<TOKEN>/setWebhook?url=<webhook_url>&secret_token=<secret_token>'"
    }
