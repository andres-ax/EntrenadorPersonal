# Structured Outputs, Streaming y Tracing

Doc oficial:
- Agents (output_type): https://openai.github.io/openai-agents-python/agents/
- Streaming: https://openai.github.io/openai-agents-python/streaming/
- Tracing: https://openai.github.io/openai-agents-python/tracing/

## Structured Outputs (output_type)

### Por que usar

Obligar al agente a devolver un objeto tipado (Pydantic) en lugar de texto libre. El SDK valida el output contra el schema; si no coincide, reintentara (o levantara error segun config).

### Ejemplo: rutina estructurada

```python
from pydantic import BaseModel, Field
from agents import Agent, Runner

class Ejercicio(BaseModel):
    nombre: str
    series: int = Field(ge=1, le=10)
    reps: str  # puede ser "8-12" rango
    rpe: float = Field(ge=1, le=10)
    descanso_seg: int

class RutinaDia(BaseModel):
    dia: int
    foco: str
    ejercicios: list[Ejercicio]
    duracion_estimada_min: int

class PlanSemanal(BaseModel):
    titulo: str
    dias: list[RutinaDia]
    deload_cada_n_semanas: int

planificador = Agent(
    name="Planificador",
    instructions="Generas planes semanales basados en NSCA-CSCS...",
    output_type=PlanSemanal,
)

result = await Runner.run(planificador, "Plan 4 dias upper/lower para intermedio")
plan: PlanSemanal = result.final_output  # ya tipado!
for dia in plan.dias:
    print(f"Dia {dia.dia}: {dia.foco}")
```

Beneficios:

- Cero parsing manual de texto del LLM
- Validacion automatica de rangos (RPE 1-10, series 1-10)
- Type safety en el resto del codigo

### Cuando NO usar

- Conversacion natural (la respuesta del coach al usuario es texto libre).
- Cuando necesitas mezclar texto explicativo + datos estructurados (usa el texto + una tool que persiste datos).

EntrenadorAX podria adoptar `output_type` para una futura tool "generar plan semanal" que devuelva un `PlanSemanal` para guardarlo en DB.

## Streaming

### Para que sirve

Mostrar al usuario los tokens conforme llegan en lugar de esperar a `final_output`. Mejora la UX percibida (especialmente en respuestas largas).

### Patron con Telegram

Telegram NO soporta streaming nativo, pero puedes:

1. **Edit message en intervalos**: enviar mensaje inicial, ir editandolo cada N tokens.
2. **Typing action mientras esperas**: ya implementado en `update.message.chat.send_action("typing")` ([src/telegram/handlers.py](../../../../src/telegram/handlers.py)).

Para chat web (futuro), si EntrenadorAX agrega frontend:

```python
result = Runner.run_streamed(coach, msg, session=session)

async for event in result.stream_events():
    if event.type == "raw_response_event":
        if event.data.type == "response.output_text.delta":
            print(event.data.delta, end="", flush=True)
    elif event.type == "tool_call_event":
        print(f"\n[Tool: {event.tool_call.name}]")
    elif event.type == "agent_updated_stream_event":
        print(f"\n[Handoff a: {event.new_agent.name}]")
```

### Eventos disponibles

| Evento | Cuando |
|---|---|
| `raw_response_event` | Tokens del LLM (delta) |
| `tool_call_event` | El agente decide llamar una tool |
| `tool_output_event` | La tool devolvio resultado |
| `agent_updated_stream_event` | Handoff a otro agente |
| `final_output_event` | Output final disponible |

### Para EntrenadorAX (futuro)

Si en algun momento la respuesta del coach es lenta (>4 segundos), implementar streaming con edit message:

```python
sent_msg = await update.message.reply_text("...")
buffer = ""
last_edit = time.time()

result = Runner.run_streamed(coach, prompt, session=session)
async for event in result.stream_events():
    if event.type == "raw_response_event" and event.data.type == "response.output_text.delta":
        buffer += event.data.delta
        if time.time() - last_edit > 1.5:  # edit cada 1.5s para no rate-limit
            await sent_msg.edit_text(buffer + "...")
            last_edit = time.time()

await sent_msg.edit_text(buffer)  # final
```

## Tracing

### Que es

El SDK genera traces automaticos de cada run: prompts enviados, tool calls, outputs, latencias, tokens. Disponibles en https://platform.openai.com/traces.

### Activar / desactivar

Por defecto: ACTIVO.

```python
import os
os.environ["OPENAI_AGENTS_DISABLE_TRACING"] = "1"  # desactivar
```

En EntrenadorAX recomendado: **MANTENER ACTIVO en produccion**. El costo es minimo y debug es 10x mas rapido.

### Que ver en cada trace

1. **Inputs**: que mensaje recibio el agente
2. **Tool calls**: que tools llamo, con que args, que devolvieron
3. **Tokens usados**: prompt, completion, total
4. **Latencias**: cada paso del loop
5. **Errores**: stack trace si algo fallo

### Custom traces

Para agregar metadata propia (ej: telegram_id):

```python
from agents import trace

with trace(workflow_name="EntrenadorAX-chat", metadata={"telegram_id": str(uid)}):
    result = await Runner.run(coach, msg, session=session)
```

### Exportar a observabilidad propia

El SDK soporta exportar a:

- Langfuse
- AgentOps
- Helicone
- LangSmith
- Logfire (Pydantic)

Para EntrenadorAX con stack Railway/Postgres, **Pydantic Logfire** es la integracion mas natural (ya usamos pydantic-settings).

```python
import logfire
logfire.configure(token="...")
logfire.instrument_openai_agents()  # instruments el SDK automaticamente
```

Las traces aparecen en Logfire dashboard con todas las herramientas y queries SQLAlchemy correlacionadas.

## Combinando: agente con output_type + streaming + tracing

```python
from agents import Agent, Runner, trace
from pydantic import BaseModel

class Respuesta(BaseModel):
    texto_usuario: str
    accion_sugerida: str | None
    tools_a_llamar: list[str]

agente = Agent(
    name="Coach",
    instructions="...",
    output_type=Respuesta,
)

with trace(workflow_name="coach-run", metadata={"uid": str(uid)}):
    result = Runner.run_streamed(agente, prompt, session=session)
    async for event in result.stream_events():
        # ... stream events
        pass

respuesta: Respuesta = result.final_output  # tipado garantizado
```
