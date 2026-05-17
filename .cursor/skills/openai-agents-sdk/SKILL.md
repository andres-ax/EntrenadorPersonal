---
name: openai-agents-sdk
description: Conocimiento experto del SDK oficial openai-agents Python (>=0.14) usado por EntrenadorAX. Cubre Agent, Runner, function_tool, RedisSession, SessionSettings, RunConfig, handoffs, guardrails, structured outputs, streaming y tracing. Use proactively al editar src/coach.py o src/tools.py, al disenar nuevas tools, al cambiar la sesion de memoria, al agregar agentes especialistas (handoffs), al implementar validacion (guardrails), o cuando el usuario discuta arquitectura del agente IA.
---

# OpenAI Agents Python SDK

Documentacion oficial: https://openai.github.io/openai-agents-python/

SDK oficial de OpenAI para construir agentes con tools, sesiones, handoffs y guardrails. Reemplaza el uso manual de chat completions con un loop estructurado y observable.

## Conceptos clave

| Concepto | Que es |
|---|---|
| `Agent` | Configuracion: instructions (system prompt), tools, output_type, guardrails, handoffs |
| `Runner.run(agent, input, session, run_config)` | Ejecuta el loop async: LLM call -> tool calls -> ... hasta tener `final_output` |
| `function_tool` | Decorador que convierte una funcion Python en tool del agente; el docstring + type hints generan el schema JSON |
| `Session` | Memoria conversacional persistente (SQLite, Redis, OpenAI Conversations API, custom) |
| `SessionSettings(limit=N)` | Limita cuantos items del historial se traen por turno (control de tokens) |
| `RunConfig` | Config por-run: session_settings, model overrides, tracing, callbacks |
| `Handoff` | Delegacion a otro Agent especialista; el LLM lo ve como una tool especial |
| `Guardrail` | Validacion input/output (puede abortar el run con tripwire) |
| `output_type` | Tipo Pydantic para forzar respuesta estructurada |

## Patron base que usa EntrenadorAX

Ver [src/coach.py](../../../src/coach.py) y [src/telegram/handlers.py](../../../src/telegram/handlers.py).

```python
from agents import Agent, RunConfig, Runner, SessionSettings
from agents.extensions.memory import RedisSession

coach = Agent(
    name="EntrenadorAX",
    instructions="Eres EntrenadorAX...",
    tools=[registrar_entreno, guardar_perfil, ...],
)

RUN_CONFIG = RunConfig(session_settings=SessionSettings(limit=20))

session = RedisSession.from_url(str(uid), url=settings.redis_url)
try:
    result = await Runner.run(coach, prompt, session=session, run_config=RUN_CONFIG)
    output = result.final_output
finally:
    await session.close()
```

## Reglas duras

1. **NUNCA combinar `session` con `conversation_id` o `previous_response_id`** en el mismo run -> error.
2. **`session.close()` SIEMPRE** en `finally` para liberar el cliente Redis (solo si se creo con `from_url`).
3. **`SessionSettings(limit=N)`**: ajustar para no explotar tokens. EntrenadorAX usa 20.
4. **Tools devuelven `str`** (JSON serializado). El SDK las inyecta en el modelo como string.
5. **Tools NUNCA lanzan excepciones** al usuario final; capturan y devuelven `{"ok": False, "error": "..."}`.
6. **Docstring Google-style obligatorio**: el SDK lo usa para construir el schema que ve el LLM. Sin docstring, el agente no sabra cuando usar la tool.
7. **Type hints simples**: `int`, `float`, `str`, `bool`. Para listas/dicts complejos usar `str` JSON-serializado y parsearlo dentro de la tool.

## Cuando leer cada referencia

| Tema | Referencia |
|---|---|
| Cambiar sesion (TTL, key prefix, custom backend, SQLite vs Redis) | [referencias/sessions.md](referencias/sessions.md) |
| Agregar/modificar tools, schemas, manejo de errores en tools | [referencias/tools.md](referencias/tools.md) |
| Agregar agentes especialistas (handoffs) y guardrails | [referencias/handoffs-guardrails.md](referencias/handoffs-guardrails.md) |
| Salidas estructuradas, streaming, tracing/observabilidad | [referencias/structured-streaming-tracing.md](referencias/structured-streaming-tracing.md) |

## Anti-patrones comunes

### Tool con tipo complejo
```python
# BAD - el SDK no genera schema limpio para Dict[str, List[...]]
@function_tool
async def registrar(data: dict[str, list[dict]]) -> str: ...

# GOOD - usar str JSON, parsear dentro
@function_tool
async def registrar(ejercicios_json: str) -> str:
    """...
    Args:
        ejercicios_json: JSON array, ej: [{"nombre":"sentadilla","reps":8}]
    """
    ejercicios = _safe_json_loads(ejercicios_json, [])
```

### Tool sin docstring
```python
# BAD - el LLM no sabra cuando usarla
@function_tool
async def obtener_pr(telegram_id: int, ejercicio: str) -> str:
    return json.dumps(...)

# GOOD
@function_tool
async def obtener_pr(telegram_id: int, ejercicio: str) -> str:
    """Consulta el Personal Record de un ejercicio.

    Args:
        telegram_id: ID del usuario
        ejercicio: nombre del ejercicio (ej: sentadilla, press banca)
    """
```

### Olvidar `session.close()`
```python
# BAD - leak de conexiones Redis
session = RedisSession.from_url(uid, url=...)
result = await Runner.run(coach, msg, session=session)
return result.final_output  # session nunca se cierra

# GOOD - try/finally
session = RedisSession.from_url(uid, url=...)
try:
    result = await Runner.run(coach, msg, session=session)
    return result.final_output
finally:
    await session.close()
```

### Pasar tool a multiples agentes sin pensar en handoffs
```python
# BAD - duplicar logica en varios agentes
coach_general = Agent(tools=[registrar_entreno, guardar_perfil])
coach_nutricion = Agent(tools=[registrar_comida, registrar_entreno])  # solapa

# GOOD - handoffs entre especialistas
coach_general = Agent(handoffs=[coach_nutricion, coach_fuerza])
coach_nutricion = Agent(tools=[registrar_comida, resumen_nutricional])
coach_fuerza = Agent(tools=[registrar_entreno, guardar_pr])
```

## Tracing y observabilidad

El SDK genera traces automaticamente; visualizables en https://platform.openai.com/traces. Para apagarlo localmente:

```python
import os
os.environ["OPENAI_AGENTS_DISABLE_TRACING"] = "1"
```

Mantener tracing ACTIVO en produccion para debug de tool calls fallidos.

## Migracion / breaking changes a observar

- 0.14+ cambio `Runner.run_streamed` -> usa `Runner.run_stream` (verificar version exacta antes de cambiar).
- `session_input_callback` es relativamente nuevo; combinar con `SessionSettings(limit=N)` para control fino.
- `RedisSession.from_url(session_id, *, url=...)` tiene argumentos kwonly desde 0.13.
