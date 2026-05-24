"""Handlers por task_type para el dispatcher."""
from __future__ import annotations

import logging
from typing import Awaitable, Callable

from telegram import Bot

logger = logging.getLogger(__name__)

HandlerFn = Callable[[Bot, dict], Awaitable[None]]

_HANDLERS: dict[str, HandlerFn] = {}


def register_handler(task_type: str, fn: HandlerFn) -> None:
    _HANDLERS[task_type] = fn


def get_handler(task_type: str) -> HandlerFn | None:
    return _HANDLERS.get(task_type)


def _register_all() -> None:
    from src.tasks.handlers import digest, escalacion, hidratacion, recordatorio, deporte

    register_handler("recordatorio", recordatorio.handle)
    register_handler("digest_matutino", digest.handle)
    register_handler("escalacion", escalacion.handle)
    register_handler("hidratacion", hidratacion.handle)
    register_handler("deporte_skill", deporte.handle)


_register_all()
