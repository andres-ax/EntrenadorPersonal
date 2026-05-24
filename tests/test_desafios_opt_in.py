"""Tests opt-in helpers (mock DB)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.comunidad import activar_desafios, desactivar_desafios


@pytest.mark.asyncio
async def test_activar_desafios_usuario_existe():
    user = MagicMock()
    user.desafios_opt_in = False

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    with patch("src.services.comunidad.async_session_factory") as factory:
        factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)
        ok = await activar_desafios(123)
    assert ok is True
    assert user.desafios_opt_in is True


@pytest.mark.asyncio
async def test_desactivar_desafios():
    user = MagicMock()
    user.desafios_opt_in = True

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    with patch("src.services.comunidad.async_session_factory") as factory:
        factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)
        ok = await desactivar_desafios(456)
    assert ok is True
    assert user.desafios_opt_in is False
