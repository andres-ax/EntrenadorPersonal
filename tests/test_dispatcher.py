"""Tests dispatcher y cap proactivo."""
from __future__ import annotations

import pytest

from src.services import proactive_limit as pl


@pytest.mark.asyncio
async def test_cap_proactivo(monkeypatch):
    counts: dict[str, int] = {}

    class FakeRedis:
        async def get(self, key):
            return counts.get(key, 0)

        async def incr(self, key):
            counts[key] = int(counts.get(key, 0)) + 1
            return counts[key]

        async def expire(self, key, ttl):
            pass

    async def fake_fecha(_uid):
        from datetime import date
        return date(2026, 5, 23)

    monkeypatch.setattr(pl, "fecha_hoy_usuario", fake_fecha)
    async def fake_get_redis():
        return FakeRedis()

    monkeypatch.setattr(pl, "get_redis", fake_get_redis)
    monkeypatch.setattr(pl.settings, "max_proactive_msgs_per_day", 3)

    assert await pl.puede_enviar_proactivo(1) is True
    await pl.registrar_envio_proactivo(1)
    await pl.registrar_envio_proactivo(1)
    await pl.registrar_envio_proactivo(1)
    assert await pl.puede_enviar_proactivo(1) is False
