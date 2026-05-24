"""Regresion: callbacks del menu + requiere_tier no deben crashear."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db.models import PlanSuscripcion
from src.telegram.decoradores import requiere_tier
from src.telegram.handlers import _FakeUpdate


@pytest.mark.asyncio
async def test_fake_update_expone_effective_message():
    msg = MagicMock()
    user = MagicMock(id=123)
    fake = _FakeUpdate(msg, user)
    assert fake.effective_message is msg


@pytest.mark.asyncio
async def test_requiere_tier_responde_upsell_desde_fake_update():
    msg = MagicMock()
    msg.reply_text = AsyncMock()
    user = MagicMock(id=456)

    @requiere_tier(PlanSuscripcion.STARTER)
    async def handler(update, ctx):
        await update.message.reply_text("ok")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "src.telegram.decoradores.es_plan_minimo",
            AsyncMock(return_value=False),
        )
        mp.setattr(
            "src.telegram.decoradores.obtener_plan_actual",
            AsyncMock(return_value=PlanSuscripcion.FREE),
        )
        await handler(_FakeUpdate(msg, user), MagicMock())

    msg.reply_text.assert_awaited_once()
    assert "Starter" in msg.reply_text.await_args.args[0]
