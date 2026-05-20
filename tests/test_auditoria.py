"""Suite de pruebas para la capa de auditoría persistente de turnos y tools."""
from __future__ import annotations

import json
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.admin import detalle_auditoria, listar_auditoria
from src.db.models import AuditoriaTurno
from src.db.repository import grabar_auditoria_turno
from src.telegram.handlers import _procesar
from src.telegram.permissions import current_turn_tools
from src.tools import _log_tool


class MockResult:
    """Clase helper simple para simular los resultados de SQLAlchemy de forma síncrona."""

    def __init__(self, data=None, scalar_val=None):
        self._data = data or []
        self._scalar_val = scalar_val

    def scalars(self):
        class ScalarsProxy:
            def __init__(self, d):
                self._d = d

            def all(self):
                return self._d

        return ScalarsProxy(self._data)

    def scalar(self):
        return self._scalar_val

    def scalar_one_or_none(self):
        return self._scalar_val


def setup_mock_session_factory(execute_mock=None):
    """Helper para crear una fábrica de sesiones SQLAlchemy que se comporte correctamente
    dentro de un bloque 'async with async_session_factory() as session:'.
    """
    mock_session_instance = AsyncMock()
    mock_session_instance.add = MagicMock()
    mock_session_instance.commit = AsyncMock()
    mock_session_instance.close = AsyncMock()

    if execute_mock is not None:
        mock_session_instance.execute = execute_mock
    else:
        mock_session_instance.execute = AsyncMock(return_value=MockResult(scalar_val=None))

    mock_factory = MagicMock()
    mock_factory.__aenter__ = AsyncMock(return_value=mock_session_instance)
    mock_factory.__aexit__ = AsyncMock(return_value=None)
    
    # También permitir invocar la fábrica como callable normal que devuelva el context manager
    mock_factory.return_value = mock_factory
    
    return mock_factory, mock_session_instance


@pytest.mark.asyncio
async def test_grabar_auditoria_turno_exito():
    # Configurar el resultado de execute usando nuestro helper síncrono MockResult
    mock_execute = AsyncMock(return_value=MockResult(scalar_val=None))
    mock_factory, mock_session = setup_mock_session_factory(execute_mock=mock_execute)

    with patch("src.db.repository.async_session_factory", mock_factory):
        await grabar_auditoria_turno(
            telegram_id=12345,
            request_id="req-test-123",
            prompt_usuario="Hola coach",
            respuesta_bot="Hola, ¿cómo estás?",
            tools_invocadas=[{"tool_name": "test_tool"}],
            tokens_input=10,
            tokens_output=20,
            costo_estimado_usd=0.0001,
            duracion_ms=150,
            error=None,
        )

        # Verificar que se añadió a la sesión
        mock_session.add.assert_called_once()
        added_obj = mock_session.add.call_args[0][0]
        assert isinstance(added_obj, AuditoriaTurno)
        assert added_obj.telegram_id == 12345
        assert added_obj.request_id == "req-test-123"
        assert added_obj.prompt_usuario == "Hola coach"
        assert added_obj.respuesta_bot == "Hola, ¿cómo estás?"
        assert added_obj.tools_invocadas == [{"tool_name": "test_tool"}]
        assert added_obj.tokens_input == 10
        assert added_obj.tokens_output == 20
        assert added_obj.duracion_ms == 150
        assert added_obj.error is None
        mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_grabar_auditoria_turno_fallo_no_rompe_flujo():
    # Si la base de datos lanza un error, grabar_auditoria_turno no debe levantar una excepción
    mock_execute = AsyncMock(side_effect=Exception("Conexión perdida con Postgres"))
    mock_factory, _ = setup_mock_session_factory(execute_mock=mock_execute)

    with patch("src.db.repository.async_session_factory", mock_factory):
        # Esta llamada NO debe levantar excepción
        await grabar_auditoria_turno(
            telegram_id=12345,
            request_id="req-fail-123",
            prompt_usuario="Hola coach",
            respuesta_bot="Hola",
        )


@pytest.mark.asyncio
async def test_decorador_log_tool_guarda_en_contextvar():
    # Inicializamos la variable de contexto de tools del turno actual
    token = current_turn_tools.set([])

    try:

        @_log_tool
        async def dummy_tool(telegram_id: int, param: str):
            return json.dumps({"ok": True, "result": f"recibido: {param}"})

        res = await dummy_tool(12345, "pesas")
        assert "recibido: pesas" in res

        tools_list = current_turn_tools.get()
        assert tools_list is not None
        assert len(tools_list) == 1
        assert tools_list[0]["tool_name"] == "dummy_tool"
        assert tools_list[0]["args"] == [12345, "pesas"]
        assert tools_list[0]["ok"] is True
        assert tools_list[0]["elapsed_ms"] >= 0
    finally:
        current_turn_tools.reset(token)


@pytest.mark.asyncio
async def test_procesar_guarda_auditoria_exito():
    mock_message = AsyncMock()
    mock_message.reply_text = AsyncMock()

    # Mockear Runner.run para simular la llamada de IA exitosa
    mock_runner_result = MagicMock()
    mock_runner_result.final_output = "Entendido, ya lo guardé."
    # Mockear usage de tokens
    mock_response = MagicMock()
    mock_response.usage.input_tokens = 50
    mock_response.usage.output_tokens = 30
    mock_runner_result.raw_responses = [mock_response]

    # Mockear SafeRedisSession para evitar fallas de await session.close()
    mock_redis_session = MagicMock()
    mock_redis_session.close = AsyncMock()

    # Mockear las dependencias de _procesar
    with (
        patch("src.telegram.handlers._build_prompt", AsyncMock(return_value="prompt-test")),
        patch("src.telegram.handlers.SafeRedisSession.from_url", MagicMock(return_value=mock_redis_session)),
        patch("src.telegram.handlers.Runner.run", AsyncMock(return_value=mock_runner_result)),
        patch("src.telegram.handlers.log_llm_usage", AsyncMock()),
        patch("src.db.repository.grabar_auditoria_turno", AsyncMock()) as mock_grabar,
    ):
        await _procesar(
            message=mock_message,
            texto="Hola, quiero entrenar",
            uid=12345,
            with_keyboard=False,
            ctx=None,
        )

        # Verificar que se llamó a grabar_auditoria_turno
        mock_grabar.assert_called_once()
        call_kwargs = mock_grabar.call_args[1]
        assert call_kwargs["telegram_id"] == 12345
        assert call_kwargs["prompt_usuario"] == "Hola, quiero entrenar"
        assert call_kwargs["respuesta_bot"] == "Entendido, ya lo guardé."
        assert call_kwargs["tokens_input"] == 50
        assert call_kwargs["tokens_output"] == 30
        assert call_kwargs["duracion_ms"] >= 0
        assert call_kwargs["error"] is None


@pytest.mark.asyncio
async def test_procesar_captura_error_guardrail():
    mock_message = AsyncMock()
    mock_message.reply_text = AsyncMock()

    from agents import InputGuardrailTripwireTriggered

    # Crear un error de guardrail ficticio con la estructura correcta
    mock_guardrail_res = MagicMock()
    mock_guardrail_res.guardrail.__class__.__name__ = "GuardrailRedFlagsMedicos"
    mock_guardrail_res.guardrail.name = "guardrail_red_flags_medicos"
    e = InputGuardrailTripwireTriggered(mock_guardrail_res)

    # Mockear SafeRedisSession para evitar fallas de await session.close()
    mock_redis_session = MagicMock()
    mock_redis_session.close = AsyncMock()

    with (
        patch("src.telegram.handlers._build_prompt", AsyncMock(return_value="prompt-test")),
        patch("src.telegram.handlers.SafeRedisSession.from_url", MagicMock(return_value=mock_redis_session)),
        patch("src.telegram.handlers.Runner.run", AsyncMock(side_effect=e)),
        patch("src.db.repository.grabar_auditoria_turno", AsyncMock()) as mock_grabar,
    ):
        await _procesar(
            message=mock_message,
            texto="Me duele el pecho fuerte",
            uid=12345,
            with_keyboard=False,
            ctx=None,
        )

        # Verificar que se grabó la auditoría indicando el error de guardrail médico
        mock_grabar.assert_called_once()
        call_kwargs = mock_grabar.call_args[1]
        assert call_kwargs["telegram_id"] == 12345
        assert call_kwargs["prompt_usuario"] == "Me duele el pecho fuerte"
        assert call_kwargs["respuesta_bot"] is None
        assert "guardrail_red_flags_medicos" in call_kwargs["error"]


@pytest.mark.asyncio
async def test_endpoints_admin_auditoria():
    mock_admin_payload = {"email": "admin@ax.com", "rol": "super"}

    mock_turno = AuditoriaTurno(
        id=1,
        telegram_id=12345,
        usuario_id=10,
        request_id="req-999",
        prompt_usuario="Hola",
        respuesta_bot="Mundo",
        tokens_input=5,
        tokens_output=5,
        costo_estimado_usd=0.0,
        duracion_ms=100,
        error=None,
        creado_en=datetime.now(),
    )

    # Configurar side_effect para devolver primero el total (1) y luego la lista de turnos
    call_count = 0
    def mock_execute_fn(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MockResult(scalar_val=1)
        else:
            return MockResult(data=[mock_turno])

    mock_execute = AsyncMock(side_effect=mock_execute_fn)
    mock_factory, _ = setup_mock_session_factory(execute_mock=mock_execute)

    with patch("src.api.admin.async_session_factory", mock_factory):
        res = await listar_auditoria(
            admin=mock_admin_payload,
            telegram_id=12345,
            request_id=None,
            con_error=None,
            limit=50,
            offset=0,
        )

        assert res["total"] == 1
        assert len(res["items"]) == 1
        assert res["items"][0]["request_id"] == "req-999"
        assert res["items"][0]["prompt_usuario"] == "Hola"

    # Mockear resultado de execute para detalle_auditoria
    mock_execute_detail = AsyncMock(return_value=MockResult(scalar_val=mock_turno))
    mock_factory_detail, _ = setup_mock_session_factory(execute_mock=mock_execute_detail)

    with patch("src.api.admin.async_session_factory", mock_factory_detail):
        res_det = await detalle_auditoria(request_id="req-999", admin=mock_admin_payload)

        assert res_det["request_id"] == "req-999"
        assert res_det["prompt_usuario"] == "Hola"
        assert res_det["respuesta_bot"] == "Mundo"
