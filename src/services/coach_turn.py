"""Nucleo canal-agnostico del coach: Runner + RedisSession + persistencia."""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

import openai
from agents import (
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    RunConfig,
    Runner,
    SessionSettings,
)

from src.cache import limpiar_keys_usuario
from src.coach import coach
from src.config import settings
from src.db.models import CanalConversacion, RolMensajeChat
from src.db.repository import grabar_auditoria_turno, log_evento, log_llm_usage
from src.services.coach_context import build_coach_prompt
from src.services.coach_output import aplicar_guardrails_output
from src.services.conversation_service import (
    guardar_mensaje,
    obtener_conversacion_por_id,
    session_key_for_conversacion,
)
from src.telegram.permissions import current_session_uid, current_turn_tools
from src.telegram.safe_session import SafeRedisSession

logger = logging.getLogger(__name__)

RUN_CONFIG = RunConfig(session_settings=SessionSettings(limit=settings.session_limit))

CanalCoach = Literal["telegram", "android"]


@dataclass
class CoachTurnResult:
    respuesta: str
    tools_invocadas: list[dict] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    request_id: str = ""
    error: str | None = None
    guardrail: str | None = None
    mensaje_usuario_id: int | None = None
    mensaje_coach_id: int | None = None


def _canal_enum(canal: CanalCoach) -> CanalConversacion:
    return CanalConversacion.TELEGRAM if canal == "telegram" else CanalConversacion.ANDROID


def _es_desde_telegram(canal: CanalCoach) -> bool:
    return canal == "telegram"


async def _run_agent_once(
    prompt: str,
    session: SafeRedisSession,
    telegram_id: int,
) -> tuple[str, int, int]:
    result = await Runner.run(coach, prompt, session=session, run_config=RUN_CONFIG)
    output = result.final_output or ""
    tokens_in = 0
    tokens_out = 0
    if result.raw_responses:
        try:
            tokens_in = sum(r.usage.input_tokens for r in result.raw_responses if r.usage)
            tokens_out = sum(r.usage.output_tokens for r in result.raw_responses if r.usage)
            await log_llm_usage(
                telegram_id,
                "coach",
                settings.coach_model,
                tokens_in,
                tokens_out,
                rounds=len(result.raw_responses),
            )
        except Exception:
            pass
    tools = current_turn_tools.get() or []
    output, _eventos = aplicar_guardrails_output(output, tools)
    return output, tokens_in, tokens_out


async def run_coach_turn(
    *,
    telegram_id: int,
    conversacion_id: int,
    texto: str,
    canal: CanalCoach,
    conversacion_titulo: str | None = None,
    metadata_usuario: dict | None = None,
    skip_persist_user: bool = False,
) -> CoachTurnResult:
    """Ejecuta un turno completo del coach y persiste mensajes."""
    t_start = time.perf_counter()
    request_id = uuid.uuid4().hex
    canal_db = _canal_enum(canal)
    es_tg = _es_desde_telegram(canal)

    token_uid = current_session_uid.set(telegram_id)
    token_tools = current_turn_tools.set([])

    user_msg_id: int | None = None
    if not skip_persist_user:
        user_msg = await guardar_mensaje(
            conversacion_id,
            RolMensajeChat.USER,
            texto,
            canal_db,
            es_desde_telegram=es_tg,
            metadata=metadata_usuario,
        )
        user_msg_id = user_msg.id

    conv_row = await obtener_conversacion_por_id(conversacion_id)
    usuario_id = conv_row.usuario_id if conv_row else None
    if usuario_id:
        try:
            from src.services.chat_events import emit_coach_typing

            await emit_coach_typing(usuario_id, conversacion_id, True)
        except Exception:
            pass

    respuesta_bot: str | None = None
    tokens_in = 0
    tokens_out = 0
    error_message: str | None = None
    guardrail: str | None = None

    session = SafeRedisSession.from_url(
        session_key_for_conversacion(conversacion_id),
        url=settings.redis_url_str,
        ttl=settings.session_ttl_seconds,
    )

    try:
        prompt = await build_coach_prompt(
            texto,
            telegram_id,
            conversacion_titulo=conversacion_titulo,
            conversacion_id=conversacion_id,
            canal=canal,
        )
        try:
            try:
                output, tokens_in, tokens_out = await _run_agent_once(
                    prompt, session, telegram_id
                )
                respuesta_bot = output
            except InputGuardrailTripwireTriggered as e:
                guardrail_obj = getattr(getattr(e, "guardrail_result", None), "guardrail", None)
                g_name = getattr(guardrail_obj, "name", "")
                guardrail = g_name or "input_guardrail"
                error_message = f"InputGuardrailTripwireTriggered: {g_name}"
                if "red_flags" in g_name:
                    respuesta_bot = (
                        "Atencion medica recomendada. Lo que describes puede ser un sintoma "
                        "de alerta. Deten la actividad fisica y busca valoracion medica si persiste."
                    )
                elif "anti_pollution" in g_name:
                    respuesta_bot = (
                        "Mi rol es ser tu coach deportivo. Volvamos a entrenamientos, comidas y descanso."
                    )
                else:
                    respuesta_bot = "Ese mensaje no se ve bien. Intentalo de nuevo con algo mas claro."
            except OutputGuardrailTripwireTriggered:
                guardrail = "output_guardrail"
                error_message = "OutputGuardrailTripwireTriggered"
                respuesta_bot = (
                    "Note algo en mi respuesta que prefiero no afirmar. Lo correcto es "
                    "que un profesional medico evalue tu caso. Sigamos con habitos concretos."
                )
                await log_evento(telegram_id, "output_guardrail_diagnostico", {"source": "sdk"})
            except openai.BadRequestError as e:
                if "No tool call found" not in str(e):
                    raise
                logger.warning("Sesion Redis corrupta conv=%s, reintentando", conversacion_id)
                try:
                    await session.close()
                except Exception:
                    pass
                await limpiar_keys_usuario(telegram_id)
                await log_evento(
                    telegram_id,
                    "sesion_redis_recuperada",
                    {"error": str(e)[:200], "conversacion_id": conversacion_id},
                )
                session = SafeRedisSession.from_url(
                    session_key_for_conversacion(conversacion_id),
                    url=settings.redis_url_str,
                    ttl=settings.session_ttl_seconds,
                )
                output, tokens_in, tokens_out = await _run_agent_once(
                    prompt, session, telegram_id
                )
                respuesta_bot = output
        except Exception as e:
            logger.exception("Error coach turn uid=%s conv=%s", telegram_id, conversacion_id)
            error_message = f"{type(e).__name__}: {e}"
            respuesta_bot = "Tuve un saltico tecnico. Vuelve a escribirme y arrancamos."
        finally:
            await session.close()
            if usuario_id:
                try:
                    from src.services.chat_events import emit_coach_typing

                    await emit_coach_typing(usuario_id, conversacion_id, False)
                except Exception:
                    pass
    finally:
        current_session_uid.reset(token_uid)
        tools_invocadas = current_turn_tools.get() or []
        current_turn_tools.reset(token_tools)

        coach_msg_id: int | None = None
        if respuesta_bot:
            coach_msg = await guardar_mensaje(
                conversacion_id,
                RolMensajeChat.ASSISTANT,
                respuesta_bot,
                canal_db,
                es_desde_telegram=es_tg,
                metadata={
                    "request_id": request_id,
                    "tools_invocadas": tools_invocadas,
                },
            )
            coach_msg_id = coach_msg.id

        duracion_ms = int((time.perf_counter() - t_start) * 1000)
        costo = (tokens_in / 1_000_000) * 0.15 + (tokens_out / 1_000_000) * 0.60
        if settings.coach_model in ("gpt-4o", "gpt-4"):
            costo = (tokens_in / 1_000_000) * 2.50 + (tokens_out / 1_000_000) * 10.00

        await grabar_auditoria_turno(
            telegram_id=telegram_id,
            request_id=request_id,
            prompt_usuario=texto,
            respuesta_bot=respuesta_bot,
            tools_invocadas=tools_invocadas,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            costo_estimado_usd=costo,
            duracion_ms=duracion_ms,
            error=error_message,
            conversacion_id=conversacion_id,
            canal=canal,
        )

    return CoachTurnResult(
        respuesta=respuesta_bot or "",
        tools_invocadas=tools_invocadas,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        request_id=request_id,
        error=error_message,
        guardrail=guardrail,
        mensaje_usuario_id=user_msg_id,
        mensaje_coach_id=coach_msg_id,
    )


async def run_coach_turn_stream(
    *,
    telegram_id: int,
    conversacion_id: int,
    texto: str,
    canal: CanalCoach,
    conversacion_titulo: str | None = None,
    metadata_usuario: dict | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Ejecuta turno del coach emitiendo eventos SSE: token, tool, done, error."""
    t_start = time.perf_counter()
    request_id = uuid.uuid4().hex
    canal_db = _canal_enum(canal)
    es_tg = _es_desde_telegram(canal)

    token_uid = current_session_uid.set(telegram_id)
    token_tools = current_turn_tools.set([])

    user_msg = await guardar_mensaje(
        conversacion_id,
        RolMensajeChat.USER,
        texto,
        canal_db,
        es_desde_telegram=es_tg,
        metadata=metadata_usuario,
    )

    conv_row = await obtener_conversacion_por_id(conversacion_id)
    usuario_id = conv_row.usuario_id if conv_row else None
    if usuario_id:
        try:
            from src.services.chat_events import emit_coach_typing

            await emit_coach_typing(usuario_id, conversacion_id, True)
        except Exception:
            pass

    respuesta_bot = ""
    tokens_in = 0
    tokens_out = 0
    error_message: str | None = None
    tools_invocadas: list[dict] = []

    session = SafeRedisSession.from_url(
        session_key_for_conversacion(conversacion_id),
        url=settings.redis_url_str,
        ttl=settings.session_ttl_seconds,
    )

    try:
        prompt = await build_coach_prompt(
            texto,
            telegram_id,
            conversacion_titulo=conversacion_titulo,
            conversacion_id=conversacion_id,
            canal=canal,
        )
        buffer = ""
        try:
            if hasattr(Runner, "run_streamed"):
                result = Runner.run_streamed(coach, prompt, session=session, run_config=RUN_CONFIG)
                async for event in result.stream_events():
                    etype = getattr(event, "type", None)
                    if etype == "raw_response_event":
                        data = getattr(event, "data", None)
                        if data and getattr(data, "type", "") == "response.output_text.delta":
                            delta = getattr(data, "delta", "") or ""
                            if delta:
                                buffer += delta
                                yield {"type": "token", "delta": delta}
                    elif etype == "tool_call_event":
                        tc = getattr(event, "tool_call", None)
                        name = getattr(tc, "name", "") if tc else ""
                        if name:
                            yield {"type": "tool", "name": name}
                respuesta_bot = buffer or (getattr(result, "final_output", None) or "")
            else:
                output, tokens_in, tokens_out = await _run_agent_once(
                    prompt, session, telegram_id
                )
                respuesta_bot = output
                yield {"type": "token", "delta": output}
        except InputGuardrailTripwireTriggered:
            respuesta_bot = "Ese mensaje no se ve bien. Intentalo de nuevo con algo mas claro."
            yield {"type": "error", "message": "input_guardrail"}
            yield {"type": "token", "delta": respuesta_bot}
        except OutputGuardrailTripwireTriggered:
            respuesta_bot = (
                "Note algo en mi respuesta que prefiero no afirmar. Consulta a un profesional."
            )
            yield {"type": "error", "message": "output_guardrail"}
            yield {"type": "token", "delta": respuesta_bot}
        except Exception as e:
            logger.exception("Error coach stream uid=%s conv=%s", telegram_id, conversacion_id)
            error_message = f"{type(e).__name__}: {e}"
            respuesta_bot = "Tuve un saltico tecnico. Vuelve a escribirme y arrancamos."
            yield {"type": "error", "message": error_message}
            yield {"type": "token", "delta": respuesta_bot}
        finally:
            await session.close()
            if usuario_id:
                try:
                    from src.services.chat_events import emit_coach_typing

                    await emit_coach_typing(usuario_id, conversacion_id, False)
                except Exception:
                    pass
    finally:
        current_session_uid.reset(token_uid)
        tools_invocadas = current_turn_tools.get() or []
        current_turn_tools.reset(token_tools)

        coach_msg_id: int | None = None
        if respuesta_bot:
            coach_msg = await guardar_mensaje(
                conversacion_id,
                RolMensajeChat.ASSISTANT,
                respuesta_bot,
                canal_db,
                es_desde_telegram=es_tg,
                metadata={"request_id": request_id, "tools_invocadas": tools_invocadas},
            )
            coach_msg_id = coach_msg.id

        duracion_ms = int((time.perf_counter() - t_start) * 1000)
        await grabar_auditoria_turno(
            telegram_id=telegram_id,
            request_id=request_id,
            prompt_usuario=texto,
            respuesta_bot=respuesta_bot or None,
            tools_invocadas=tools_invocadas,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            costo_estimado_usd=0.0,
            duracion_ms=duracion_ms,
            error=error_message,
            conversacion_id=conversacion_id,
            canal=canal,
        )

        yield {
            "type": "done",
            "respuesta": respuesta_bot,
            "mensaje_usuario_id": user_msg.id,
            "mensaje_coach_id": coach_msg_id,
            "request_id": request_id,
        }
