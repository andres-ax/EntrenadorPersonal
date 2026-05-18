"""FastAPI + webhook de Telegram. Modo produccion (Railway)."""
from __future__ import annotations

import asyncio
import hmac
import html
import json
import logging
import time
import traceback
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, Defaults

from src.api.admin_auth import seed_admin_si_falta
from src.cache import close_redis, ping as ping_redis
from src.config import settings
from src.db.connection import close_db, engine, init_db, ping as ping_db
from src.log_setup import (
    bind_request_id,
    bind_telegram_id,
    get_or_make_request_id,
    request_id_ctx,
    setup_logging,
    telegram_id_ctx,
)
from src.telegram.bot_setup import set_application, setup_bot
from src.telegram.handlers import registrar
from src.telegram.pubsub_listener import start_pubsub_listener
from src.telegram.scheduler import registrar_jobs

setup_logging()

logger = logging.getLogger(__name__)

if settings.sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn.get_secret_value(),
            environment=settings.env,
            traces_sample_rate=0.1,
            profiles_sample_rate=0.1,
            integrations=[FastApiIntegration()],
        )
        logger.info("Sentry inicializado")
    except Exception:
        logger.exception("Error inicializando Sentry")

WEBHOOK_SECRET: str = settings.webhook_secret.get_secret_value()
ADMIN_TOKEN: str = settings.admin_token.get_secret_value()

telegram_app: Application | None = None
pubsub_task: asyncio.Task | None = None


async def error_handler(update, context) -> None:
    """Captura excepciones no atrapadas y notifica al developer."""
    uid = None
    try:
        if update is not None and getattr(update, "effective_user", None):
            uid = update.effective_user.id
    except Exception:
        pass
    logger.error(
        "Excepcion en handler de Telegram uid=%s update_id=%s",
        uid,
        getattr(update, "update_id", None) if update else None,
        exc_info=context.error,
    )
    if settings.sentry_dsn:
        try:
            import sentry_sdk

            if uid is not None:
                sentry_sdk.set_user({"id": uid})
            sentry_sdk.set_tag("source", "telegram_handler")
        except Exception:
            pass
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
    try:
        from src.db.repository import cargar_catalog_en_cache

        n = await cargar_catalog_en_cache()
        logger.info("Cargados %s deportes en cache", n)
    except Exception:
        logger.exception("No pude precargar catalog de deportes")
    try:
        await seed_admin_si_falta()
    except Exception:
        logger.exception("Error en seed_admin_si_falta (no critico)")
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
    set_application(telegram_app)
    registrar(telegram_app)
    registrar_jobs(telegram_app)
    telegram_app.add_error_handler(error_handler)

    await telegram_app.initialize()
    await telegram_app.start()
    pubsub_task = start_pubsub_listener(telegram_app)
    logger.info("Telegram app inicializada + pubsub listener activo")

    # Auto-setWebhook: en cada startup registramos la URL con Telegram para
    # que los updates lleguen a /webhook. Idempotente y resiste el bug clasico
    # de "el webhook se perdio". Solo corre si WEBHOOK_BASE_URL esta seteada.
    if settings.webhook_base_url:
        webhook_url = (
            f"{str(settings.webhook_base_url).rstrip('/')}/webhook"
        )
        try:
            await telegram_app.bot.set_webhook(
                url=webhook_url,
                secret_token=WEBHOOK_SECRET,
                allowed_updates=[
                    "message",
                    "callback_query",
                    "poll_answer",
                    "message_reaction",
                    "pre_checkout_query",
                    "inline_query",
                ],
                drop_pending_updates=False,
            )
            logger.info("Webhook seteado en Telegram: %s", webhook_url)
        except Exception:
            logger.exception("No pude setear el webhook en Telegram")
    else:
        logger.warning(
            "WEBHOOK_BASE_URL no seteada; el bot no recibira updates por webhook"
        )

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


_ACCESS_LOG_SKIP_PATHS = {"/health"}


@app.middleware("http")
async def request_id_and_access_log(request: Request, call_next):
    """Inyecta request_id en ContextVar + emite un access log por request.

    Si el cliente envia `X-Request-ID` lo respetamos (util para correlar
    desde el frontend o un edge proxy). Si no, generamos uno corto.
    """
    rid = request.headers.get("x-request-id") or get_or_make_request_id()
    rid_token = request_id_ctx.set(rid)
    if settings.sentry_dsn:
        try:
            import sentry_sdk

            sentry_sdk.set_tag("request_id", rid)
        except Exception:
            pass
    t0 = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["x-request-id"] = rid
        return response
    except Exception:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.exception(
            "HTTP %s %s -> EXC rid=%s elapsed=%.1fms ip=%s",
            request.method,
            request.url.path,
            rid,
            elapsed_ms,
            request.client.host if request.client else "?",
        )
        raise
    finally:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if request.url.path not in _ACCESS_LOG_SKIP_PATHS:
            logger.info(
                "HTTP %s %s -> %d rid=%s elapsed=%.1fms ip=%s ua=%s",
                request.method,
                request.url.path,
                status_code,
                rid,
                elapsed_ms,
                request.client.host if request.client else "?",
                (request.headers.get("user-agent") or "-")[:120],
            )
        try:
            request_id_ctx.reset(rid_token)
        except Exception:
            pass


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Handler global para 500s no controlados.

    HTTPException ya tiene su propio handler en FastAPI; aqui solo entran
    excepciones genuinamente inesperadas. Devuelve un body con request_id
    para que el usuario nos lo cite y podamos buscarlo en los logs.
    """
    rid = request_id_ctx.get()
    logger.exception(
        "Unhandled exception rid=%s method=%s path=%s",
        rid,
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal Server Error",
            "request_id": rid,
        },
        headers={"x-request-id": rid},
    )


from src.api.admin import router as admin_router  # noqa: E402
from src.api.auth import router as auth_router  # noqa: E402
from src.api.integraciones import router as integraciones_router  # noqa: E402
from src.api.me import router as me_router  # noqa: E402
from src.api.public import router as public_router  # noqa: E402

# Routers HTML server-side (Jinja2). Reemplazan los antiguos frontends
# Next.js / Vite / Astro. Se montan con prioridad mayor que el StaticFiles
# de la landing para que las rutas dinamicas (/, /admin/*, /app/*) ganen.
from src.realtime.server import router as realtime_router  # noqa: E402
from src.web.admin_ui import router as admin_ui_router  # noqa: E402
from src.web.app_ui import router as app_ui_router  # noqa: E402
from src.web.landing import router as landing_router  # noqa: E402

# ORDEN IMPORTANTE: FastAPI resuelve la primera ruta coincidente. Las rutas
# HTML del admin viven en /admin/* (mismo prefijo que el JSON). Para que el
# navegador reciba HTML en GET /admin/usuarios y no el JSON 401, el
# admin_ui_router debe ir ANTES que admin_router. Los formularios HTML usan
# sufijos _form (ej. /admin/usuarios/{uid}/bloquear_form) para no chocar
# con las rutas POST JSON.
app.include_router(admin_ui_router)
app.include_router(app_ui_router)
app.include_router(realtime_router)

app.include_router(auth_router)
app.include_router(me_router)
app.include_router(admin_router)
app.include_router(public_router)
app.include_router(integraciones_router)

# Landing al final: tiene rutas catch-all (`/`) que podrian capturar otras.
app.include_router(landing_router)


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
        logger.warning("Webhook recibido pero bot no esta listo")
        raise HTTPException(503, "Bot no listo")

    if not hmac.compare_digest(
        x_telegram_bot_api_secret_token or "", WEBHOOK_SECRET
    ):
        logger.warning(
            "Webhook con secret invalido ip=%s",
            request.client.host if request.client else "?",
        )
        raise HTTPException(403, "Token invalido")

    body = await request.body()
    if len(body) > settings.max_webhook_payload_bytes:
        logger.warning("Webhook payload too large size=%d", len(body))
        raise HTTPException(413, "Payload too large")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        logger.warning("Webhook con JSON invalido size=%d", len(body))
        raise HTTPException(400, "JSON invalido")

    update = Update.de_json(data, telegram_app.bot)
    if update is None:
        logger.debug("Webhook update no parseable, ignorado")
        return {"ok": True}

    update_type = _detect_update_type(update)
    uid = update.effective_user.id if update.effective_user else None
    chat_id = update.effective_chat.id if update.effective_chat else None
    text_preview = _preview_update_text(update)
    tid_token = bind_telegram_id(uid)
    if settings.sentry_dsn and uid is not None:
        try:
            import sentry_sdk

            sentry_sdk.set_user({"id": uid})
        except Exception:
            pass
    logger.info(
        "TG update_id=%s type=%s uid=%s chat_id=%s text=%r",
        update.update_id,
        update_type,
        uid,
        chat_id,
        text_preview,
    )
    t0 = time.perf_counter()
    try:
        await telegram_app.process_update(update)
    except Exception:
        logger.exception(
            "TG process_update fallo update_id=%s type=%s uid=%s",
            update.update_id,
            update_type,
            uid,
        )
        raise
    finally:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "TG update_id=%s type=%s uid=%s procesado elapsed=%.1fms",
            update.update_id,
            update_type,
            uid,
            elapsed_ms,
        )
        try:
            telegram_id_ctx.reset(tid_token)
        except Exception:
            pass
    return {"ok": True}


def _detect_update_type(update: Update) -> str:
    """Resume el tipo de update para logs (sin reemplazar logica del bot)."""
    if update.message is not None:
        if update.message.photo:
            return "photo"
        if update.message.voice or update.message.audio:
            return "voice"
        if update.message.document:
            return "document"
        if update.message.successful_payment:
            return "payment_ok"
        return "message"
    if update.callback_query is not None:
        return "callback_query"
    if update.pre_checkout_query is not None:
        return "pre_checkout_query"
    if update.inline_query is not None:
        return "inline_query"
    if update.poll_answer is not None:
        return "poll_answer"
    if update.message_reaction is not None:
        return "message_reaction"
    return "other"


def _preview_update_text(update: Update) -> str:
    """Texto recortado del update para logs (sin loggear documentos enteros).

    Truncado a 40 chars para reducir PII en logs. Suficiente para identificar
    comando o intencion sin guardar el texto completo del usuario.
    """
    if update.message is not None and update.message.text:
        return update.message.text[:40]
    if update.callback_query is not None and update.callback_query.data:
        return f"cb:{update.callback_query.data[:40]}"
    return ""


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
async def admin_stats(
    request: Request,
    x_admin_token: str = Header(None),
) -> dict:
    """Estadisticas basicas.

    Acepta DOS formas de auth para mantener compatibilidad:
    1. Header `X-Admin-Token: <ADMIN_TOKEN>` (root, para scripts).
    2. Cookie HttpOnly `admin_jwt` (set por el panel admin tras login).

    Esto permite que el dashboard HTML del panel (que no tiene como
    pasarle el ADMIN_TOKEN al fetch del cliente) lo invoque con la
    cookie de sesion.
    """
    from datetime import date as date_t
    from datetime import timedelta

    from sqlalchemy import func, select

    from src.api.admin_auth import ADMIN_COOKIE_NAME, verify_admin_jwt
    from src.db.connection import async_session_factory
    from src.db.models import (
        CrisisLog,
        EventoBot,
        Suscripcion,
        Usuario,
    )

    autorizado = False
    if x_admin_token and hmac.compare_digest(x_admin_token, ADMIN_TOKEN):
        autorizado = True
    else:
        cookie_jwt = request.cookies.get(ADMIN_COOKIE_NAME)
        if cookie_jwt and verify_admin_jwt(cookie_jwt):
            autorizado = True
    if not autorizado:
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


# =============================================================================
# Mount /static para assets compartidos (imagenes, JS de /app/llamar, etc.)
# =============================================================================
# La landing, el admin panel y el mini app son templates Jinja2 servidos
# directamente por los routers (`src/web/*.py`). Solo necesitamos servir los
# archivos estaticos referenciados desde esos templates (/static/img/*,
# /static/js/llamar.js, etc.). El antiguo mount "/" StaticFiles que servia
# `frontend/landing/dist/` (Astro) ya no existe: lo reemplaza el router en
# `src/web/landing.py` que ya esta incluido arriba.
from pathlib import Path  # noqa: E402

from fastapi.staticfiles import StaticFiles  # noqa: E402

_static_dir = Path(__file__).resolve().parent.parent / "frontend" / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
    logger.info("Static assets montados desde %s", _static_dir)
else:
    logger.info(
        "frontend/static/ no existe; las paginas funcionan pero sin imgs/js."
    )
