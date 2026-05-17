# Sesiones (memoria conversacional)

Doc oficial: https://openai.github.io/openai-agents-python/sessions/

## Que hace una Session

- **Antes del run**: trae el historial almacenado y lo prepende al `input` del usuario.
- **Despues del run**: guarda todos los items nuevos generados (mensajes del usuario, tool calls, tool outputs, mensajes del asistente).

Implica: NO debes pasar el historial manualmente al prompt. La session se encarga.

## Implementaciones built-in

| Clase | Cuando usar |
|---|---|
| `SQLiteSession` | Local, single-user, prototipo |
| `AsyncSQLiteSession` | Local con I/O async |
| `RedisSession` | Produccion distribuida (EntrenadorAX usa esta) |
| `OpenAIConversationsSession` | Backend de OpenAI Conversations API |
| `RedisAgentMemorySession` | Alternativa Dapr / shared memory |

## RedisSession (la que usa EntrenadorAX)

### Crear desde URL

```python
from agents.extensions.memory import RedisSession

session = RedisSession.from_url(
    session_id=str(telegram_id),
    url="redis://localhost:6379/0",
    ttl=86400 * 30,                       # 30 dias de retencion
    key_prefix="entrenadorax:session:",   # evita colision con otros bots
)
```

### Argumentos importantes

| Arg | Default | Notas |
|---|---|---|
| `session_id` | requerido | Unico por conversacion (usar `str(telegram_id)` en EntrenadorAX) |
| `url` | requerido | `redis://...` o `rediss://...` (TLS) |
| `redis_kwargs` | None | dict de kwargs para `redis.asyncio.from_url` (ssl, auth, etc) |
| `ttl` | None | Segundos. Si None, sesion persiste para siempre |
| `key_prefix` | `"agents:session:"` | Cambialo si varios servicios comparten Redis |
| `session_settings` | None | `SessionSettings(limit=N)` default para esta sesion |

### Crear con cliente Redis inyectado (compartido con resto del app)

Util si ya tienes pool de conexiones (`src/telegram/middlewares.py` ya gestiona uno):

```python
import redis.asyncio as aioredis
from agents.extensions.memory import RedisSession

shared_client = aioredis.from_url(settings.redis_url, decode_responses=False)

session = RedisSession(
    session_id=str(uid),
    redis_client=shared_client,
    ttl=86400 * 30,
)
# IMPORTANTE: session.close() NO cerrara shared_client (solo cierra si fue creado via from_url)
```

### Cierre

```python
try:
    result = await Runner.run(agent, msg, session=session)
finally:
    await session.close()  # libera la conexion si fue creada con from_url
```

## SessionSettings: limitar historia

Sin limite, el SDK trae TODO el historial. Esto explota tokens con conversaciones largas.

```python
from agents import RunConfig, SessionSettings

RUN_CONFIG = RunConfig(session_settings=SessionSettings(limit=20))

result = await Runner.run(agent, msg, session=session, run_config=RUN_CONFIG)
```

- `limit=None` (default): trae todo.
- `limit=N`: solo los N items mas recientes.
- Aplicable por-run via `RunConfig.session_settings` (sobrescribe default de la sesion).

EntrenadorAX usa `limit=20` (ver `RUN_CONFIG` en handlers).

## Custom merge: `session_input_callback`

Cuando quieres logica fina de pruning/reordenamiento del historial antes del LLM:

```python
def keep_recent_history(history, new_input):
    # mantener solo ultimos 10 items + nuevo input
    return history[-10:] + new_input

RUN_CONFIG = RunConfig(session_input_callback=keep_recent_history)
```

Esto NO modifica como se guarda en Redis, solo lo que el modelo recibe ese turno.

## Borrar sesion del usuario

```python
# Opcion 1: SDK no expone clear() en RedisSession directamente
# Opcion 2: borrar keys con prefix manualmente

async def limpiar_sesion(uid: int):
    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    keys = []
    async for key in client.scan_iter(f"agents:session:{uid}*"):
        keys.append(key)
    if keys:
        await client.delete(*keys)
    await client.close()
```

EntrenadorAX usa este patron en `_limpiar_redis()` ([src/telegram/handlers.py](../../../../src/telegram/handlers.py)).

## Restricciones criticas

> Sessions cannot be combined with `conversation_id`, `previous_response_id`, or `auto_previous_response_id` in the same run.
> Documentacion oficial.

Si pasas ambos -> RunError. Elige UNO.

## TTL: cuanto guardar

Sugerencia para EntrenadorAX:

| Caso | TTL recomendado |
|---|---|
| Bot de soporte (sesiones cortas) | 24 horas |
| Bot conversacional habitual | 7-30 dias |
| Bot con contexto critico a largo plazo (perfil) | 90+ dias o None |
| Sesion sensible (compliance) | configurar TTL menor para borrado automatico |

Recordar: el PERFIL del usuario va en Postgres (durable). Lo de Redis es contexto conversacional (regenerable).

## Sesiones compartidas entre agentes

Si EntrenadorAX se divide en multiples agentes especialistas (handoffs), pueden compartir la misma session:

```python
session = RedisSession.from_url(str(uid), url=settings.redis_url)

# Coach general recibe el mensaje
result1 = await Runner.run(coach_general, mensaje_usuario, session=session)

# Si coach_general hace handoff a coach_nutricion, el contexto se preserva automatico
# (handoffs ya manejan la transicion via session)
```

## Performance

- `RedisSession` usa locks internos -> safe para concurrencia. Cada `session_id` es independiente.
- Operaciones tipicas: 1-3 round trips a Redis por turno.
- Para bots con miles de usuarios concurrentes: dimensionar Redis con maxmemory + policy `allkeys-lru` o `volatile-ttl` segun caso.
