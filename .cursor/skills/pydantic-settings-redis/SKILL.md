---
name: pydantic-settings-redis
description: Patrones para pydantic-settings v2 (BaseSettings, env_file, validacion) y redis.asyncio (cliente async, pipelines, sorted sets para rate limit, TTL, scan_iter). Cubre carga de configuracion desde .env, riesgo de I/O bloqueante en async, manejo del pool de Redis, patterns de pub/sub y locks distribuidos. Use proactively al editar src/config.py, src/telegram/middlewares.py o cuando se agreguen nuevas variables de entorno, se cambien defaults o se necesiten patrones nuevos de Redis (cache, queue, lock).
---

# Pydantic Settings v2 + Redis async

Combinacion que EntrenadorAX usa para config ([src/config.py](../../../src/config.py)) y cache/rate-limit ([src/telegram/middlewares.py](../../../src/telegram/middlewares.py)).

Docs:
- pydantic-settings: https://docs.pydantic.dev/latest/api/pydantic_settings/
- redis-py async: https://redis.readthedocs.io/en/stable/connections.html

## Pydantic Settings v2

### Patron base que usa EntrenadorAX

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    telegram_token: str = ""
    database_url: str = ""
    redis_url: str = ""
    openai_api_key: str = ""
    webhook_base_url: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

settings = Settings()
```

Lectura automatica desde:
1. Variables de entorno (case-insensitive: `TELEGRAM_TOKEN` o `telegram_token`)
2. Archivo `.env` (si existe)
3. Defaults declarados en la clase

### Tipos especializados (recomendados)

```python
from pydantic import RedisDsn, PostgresDsn, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    telegram_token: SecretStr            # no aparece en logs por default
    openai_api_key: SecretStr
    database_url: PostgresDsn            # valida que sea postgres://... valida
    redis_url: RedisDsn
    webhook_base_url: HttpUrl

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",                  # ignora vars del entorno no declaradas
    )

# Uso:
# settings.telegram_token.get_secret_value()  # acceso al valor real
# str(settings.database_url)                  # convierte a string
```

Recomendado migrar de `{"env_file": ".env", ...}` a `SettingsConfigDict(...)` (estilo v2 idiomatico).

### env_prefix (multi-servicio en mismo .env)

```python
class TelegramSettings(BaseSettings):
    token: SecretStr
    webhook_url: HttpUrl

    model_config = SettingsConfigDict(env_prefix="TELEGRAM_")

# Variables esperadas: TELEGRAM_TOKEN, TELEGRAM_WEBHOOK_URL
```

Util si tienes una app monorepo con varios servicios.

### Validacion custom

```python
from pydantic import field_validator

class Settings(BaseSettings):
    redis_url: str = ""

    @field_validator("redis_url")
    @classmethod
    def validar_redis(cls, v: str) -> str:
        if not v.startswith(("redis://", "rediss://")):
            raise ValueError("redis_url debe empezar con redis:// o rediss://")
        return v
```

### Async caveat (IMPORTANTE)

> BaseSettings initialization performs blocking I/O operations (file reads) that halt the event loop.

Si llamas `Settings()` dentro de un handler async, bloqueas el loop unos ms (leer .env, parsear). Soluciones:

1. **Singleton al startup** (lo que hace EntrenadorAX): `settings = Settings()` a nivel modulo, una sola vez.
2. **`asyncio.to_thread`** si necesitas recargar config en runtime:

```python
import asyncio

async def get_settings_async() -> Settings:
    return await asyncio.to_thread(Settings)
```

EntrenadorAX hoy usa la opcion 1 (correcto, no necesita reloading).

### Settings por entorno (dev/prod)

```python
class Settings(BaseSettings):
    env: Literal["dev", "prod", "test"] = "dev"
    # ... resto

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"
```

Tambien podes usar archivos separados:

```python
SettingsConfigDict(
    env_file=(f".env.{os.getenv('ENV', 'dev')}", ".env"),  # carga ambos, el primero tiene prioridad
)
```

### NUNCA hacer

```python
# MAL: importar settings dentro de funciones (rompe testabilidad y performance)
async def handler():
    from src.config import settings  # NO

# BIEN: import top-level
from src.config import settings

async def handler():
    client = aioredis.from_url(settings.redis_url)
```

### NUNCA leer os.getenv directamente

```python
# MAL: bypasea validacion
token = os.getenv("TELEGRAM_TOKEN")

# BIEN
from src.config import settings
token = settings.telegram_token
```

Excepcion permitida: scripts standalone (`run_bot.py`, `scripts/reset_db.py`) si necesitan `os.getenv` antes de cargar la clase.

## Redis async (redis.asyncio)

### Crear cliente

```python
import redis.asyncio as aioredis

# Mas simple (lo que usa EntrenadorAX)
client = aioredis.from_url(settings.redis_url, decode_responses=True)

# Con pool explicito (mas control)
pool = aioredis.ConnectionPool.from_url(settings.redis_url, max_connections=20)
client = aioredis.Redis(connection_pool=pool, decode_responses=True)
```

### decode_responses=True

- `True`: las respuestas son `str` (UTF-8 decoded).
- `False` (default): respuestas son `bytes`.

**EntrenadorAX usa `True` en middlewares (sorted sets de strings)** pero `False` cuando se inyecta a `RedisSession` (el SDK espera bytes).

### Singleton del cliente

```python
# src/telegram/middlewares.py
_redis_client = None

async def _get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client

async def close_redis():
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
```

Ya implementado. Cerrar siempre en el `shutdown` del lifespan.

### Pipelines (operaciones atomicas)

EntrenadorAX usa pipeline en `check_rate_limit`:

```python
pipe = client.pipeline()
pipe.zremrangebyscore(key, "-inf", now - window)  # limpiar viejos
pipe.zcard(key)                                    # contar actuales
pipe.zadd(key, {f"{now}": now})                    # agregar nuevo
pipe.expire(key, window + 1)                       # TTL
results = await pipe.execute()                     # 1 round-trip
```

Beneficio: 4 operaciones en 1 viaje a Redis en lugar de 4.

### Patrones utiles

#### Rate limit por usuario (sorted set + sliding window)

```python
async def check_rate_limit(uid: int, max_per_minute: int = 10) -> bool:
    client = await _get_redis()
    key = f"ratelimit:{uid}"
    now = time.time()
    window = 60

    pipe = client.pipeline()
    pipe.zremrangebyscore(key, "-inf", now - window)
    pipe.zcard(key)
    pipe.zadd(key, {f"{now}": now})
    pipe.expire(key, window + 1)
    results = await pipe.execute()
    count = results[1]
    return count < max_per_minute
```

Ya implementado en EntrenadorAX.

#### Cache con TTL

```python
async def cache_perfil(uid: int, perfil: dict, ttl: int = 300):
    client = await _get_redis()
    await client.set(f"perfil:{uid}", json.dumps(perfil), ex=ttl)

async def get_perfil_cached(uid: int) -> dict | None:
    client = await _get_redis()
    raw = await client.get(f"perfil:{uid}")
    return json.loads(raw) if raw else None
```

Util para evitar query DB en cada mensaje (el perfil cambia poco).

#### Borrar keys por patron (scan_iter)

```python
async def limpiar_session(uid: int):
    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    keys = []
    async for key in client.scan_iter(f"agents:session:{uid}*"):
        keys.append(key)
    if keys:
        await client.delete(*keys)
    await client.close()
```

NUNCA usar `KEYS pattern *` en produccion (bloquea Redis). SIEMPRE `SCAN`.

#### Lock distribuido

```python
async def adquirir_lock(uid: int, timeout: int = 30) -> bool:
    client = await _get_redis()
    return await client.set(f"lock:{uid}", "1", nx=True, ex=timeout)

async def liberar_lock(uid: int):
    client = await _get_redis()
    await client.delete(f"lock:{uid}")
```

Util si un mismo usuario manda 5 mensajes rapidos y solo querras procesar 1.

#### Pub/Sub

```python
async def publisher():
    client = await _get_redis()
    await client.publish("eventos:entreno", json.dumps({"uid": 123, "tipo": "fuerza"}))

async def subscriber():
    client = await _get_redis()
    pubsub = client.pubsub()
    await pubsub.subscribe("eventos:entreno")
    async for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            print(f"Evento: {data}")
```

Pendiente para EntrenadorAX si quiere disparar webhooks externos cuando se registra un entreno.

### Manejo de errores

```python
import redis.exceptions

try:
    await client.set("key", "value")
except redis.exceptions.ConnectionError:
    logger.warning("Redis no disponible, continuando sin cache")
except redis.exceptions.TimeoutError:
    logger.warning("Redis timeout")
```

NUNCA dejar que un error de Redis tumbe el bot. Patron: fallback a "sin cache" o "sin rate limit" y loggear.

EntrenadorAX ya hace esto en `check_rate_limit`:

```python
except Exception as e:
    logger.warning("Rate limit check failed: %s", e)
    return True  # permitir si Redis falla (mejor que bloquear al usuario)
```

### TTL automatico en RedisSession

El SDK de OpenAI Agents soporta TTL en `RedisSession.from_url(..., ttl=segundos)`. Para EntrenadorAX recomendado: 30 dias (memoria conversacional sin compliance estricta).

### Memory tuning de Redis

En produccion (Railway, Upstash, etc.):

| Param | Valor recomendado |
|---|---|
| `maxmemory` | Segun plan |
| `maxmemory-policy` | `allkeys-lru` (evicta lo menos usado) o `volatile-ttl` (evicta lo que vence antes) |
| `timeout` | 0 (no cerrar conexiones idle del cliente) |
| `tcp-keepalive` | 60 |

## Combinacion completa: settings + redis singleton

```python
# src/config.py
from pydantic import RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    telegram_token: SecretStr
    redis_url: RedisDsn
    # ...
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()


# src/cache.py (nuevo modulo sugerido)
import redis.asyncio as aioredis
from src.config import settings

_client: aioredis.Redis | None = None

async def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(
            str(settings.redis_url),
            decode_responses=True,
            health_check_interval=30,
            socket_keepalive=True,
        )
    return _client

async def close_redis():
    global _client
    if _client:
        await _client.aclose()
        _client = None
```

Limpieza del codigo actual: hoy el cliente de Redis se crea en 2 lugares (`middlewares.py` y `handlers.py._limpiar_redis`). Centralizar en `src/cache.py` y reusar.

## Checklist al agregar nueva variable

- [ ] Agregarla a `Settings` con tipo correcto (no usar `str` si hay tipo especializado)
- [ ] Agregar entry a `.env.example` (crear si no existe)
- [ ] Documentar en `README.md` o `INSTALL.md`
- [ ] Si es secreto, usar `SecretStr` y NUNCA loggear su valor
- [ ] Si tiene formato (URL, DSN), agregar validator
- [ ] Si depende del entorno, usar `Literal["dev", "prod"]` o pattern multi-env
