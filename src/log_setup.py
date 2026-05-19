"""Configuracion central de logging para todos los procesos de EntrenadorAX.

Llamar `setup_logging()` UNA VEZ al inicio de cada proceso (bot-api, worker,
realtime-ws). Centraliza:

- Formato JSON estructurado en prod (Railway, agregadores).
- Formato texto legible en dev.
- Niveles base por logger (silencia ruido de httpx, apscheduler, etc.).
- Filtro que inyecta `request_id` y `telegram_id` desde ContextVars.

Uso desde otros modulos:

    import logging
    logger = logging.getLogger(__name__)
    logger.info("algo paso uid=%s", uid)

Para propagar contexto desde middleware o handlers:

    from src.log_setup import request_id_ctx, telegram_id_ctx
    token = request_id_ctx.set("abc-123")
    try:
        ...
    finally:
        request_id_ctx.reset(token)
"""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

from src.config import settings

# ContextVars que se inyectan en cada log line via _ContextFilter.
# Default "-" para que el campo siempre exista en logs JSON.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
telegram_id_ctx: ContextVar[str] = ContextVar("telegram_id", default="-")


def get_or_make_request_id() -> str:
    """Devuelve un request_id corto (8 chars de uuid4) para correlacion."""
    return uuid.uuid4().hex[:12]


class _ContextFilter(logging.Filter):
    """Inyecta request_id y telegram_id desde ContextVars en cada LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        record.telegram_id = telegram_id_ctx.get()
        return True


def _build_json_formatter() -> logging.Formatter:
    """Formatter JSON estructurado para prod. Cae a texto si la lib falta."""
    try:
        from pythonjsonlogger import jsonlogger
    except ImportError:
        return _build_text_formatter()

    return jsonlogger.JsonFormatter(
        fmt=(
            "%(asctime)s %(levelname)s %(name)s %(message)s "
            "%(request_id)s %(telegram_id)s %(module)s %(funcName)s "
            "%(lineno)d"
        ),
        rename_fields={"asctime": "ts", "levelname": "level", "name": "logger"},
        json_ensure_ascii=False,
    )


def _build_text_formatter() -> logging.Formatter:
    """Formatter texto legible para dev."""
    return logging.Formatter(
        fmt=(
            "%(asctime)s [%(levelname)s] %(name)s "
            "rid=%(request_id)s tid=%(telegram_id)s | %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
    )


_LOGGER_LEVELS_PROD: dict[str, int] = {
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
    "apscheduler": logging.WARNING,
    "telegram": logging.WARNING,
    "telegram.ext": logging.WARNING,
    "sqlalchemy.engine": logging.WARNING,
    "sqlalchemy.pool": logging.WARNING,
    "asyncio": logging.WARNING,
    "openai": logging.WARNING,
    "openai.agents": logging.INFO,
    "uvicorn.access": logging.WARNING,
    "uvicorn.error": logging.INFO,
}


_already_configured = False


def setup_logging(level: int | None = None) -> None:
    """Configura el logging del proceso. Idempotente.

    Llama esto UNA VEZ al inicio del proceso (lifespan FastAPI, worker startup,
    realtime startup). No falla si se llama mas veces; solo recalcula handlers.

    Args:
        level: nivel base (DEBUG/INFO/WARNING). Si es None, se decide segun
            settings.env: DEBUG en dev, INFO en prod/test.

    """
    global _already_configured

    if level is None:
        level = logging.DEBUG if settings.env == "dev" else logging.INFO

    is_prod = settings.env in ("prod", "test")
    formatter = _build_json_formatter() if is_prod else _build_text_formatter()

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(_ContextFilter())

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(level)

    for logger_name, lvl in _LOGGER_LEVELS_PROD.items():
        logging.getLogger(logger_name).setLevel(lvl)

    _already_configured = True

    boot = logging.getLogger("src.log_setup")
    boot.info(
        "Logging configurado env=%s level=%s format=%s",
        settings.env,
        logging.getLevelName(level),
        "json" if is_prod else "text",
    )


def bind_telegram_id(telegram_id: int | str | None) -> Any:
    """Helper: setea telegram_id en el ContextVar y devuelve el token reset.

    Usar como:

        token = bind_telegram_id(uid)
        try:
            ...
        finally:
            telegram_id_ctx.reset(token)
    """
    return telegram_id_ctx.set(str(telegram_id) if telegram_id is not None else "-")


def bind_request_id(request_id: str | None) -> Any:
    """Helper: setea request_id (lo crea si es None) y devuelve token reset."""
    rid = request_id or get_or_make_request_id()
    return request_id_ctx.set(rid)
