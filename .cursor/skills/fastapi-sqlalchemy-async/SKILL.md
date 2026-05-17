---
name: fastapi-sqlalchemy-async
description: Patrones de produccion para FastAPI 0.115+ con SQLAlchemy 2.0 async y asyncpg driver. Cubre lifespan context manager, AsyncEngine, AsyncSession, async_sessionmaker, pool sizing (pool_size, max_overflow, pool_pre_ping, pool_recycle), Depends pattern para inyectar sesiones, manejo de transacciones, evitar MissingGreenlet, expire_on_commit=False y liberar sesion antes de llamadas LLM largas. Use proactively al editar src/main.py, src/db/connection.py, src/db/models.py, src/db/repository.py, al agregar endpoints, al cambiar el connection pool o al optimizar performance de queries.
---

# FastAPI + SQLAlchemy 2.0 Async + asyncpg

Stack que usa EntrenadorAX en `src/main.py` (FastAPI) y `src/db/` (SQLAlchemy async + asyncpg).

Docs oficiales:
- FastAPI lifespan: https://fastapi.tiangolo.com/advanced/events/
- SQLAlchemy async: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- asyncpg: https://magicstack.github.io/asyncpg/current/

## Arquitectura recomendada

```
FastAPI (lifespan)
  -> crea AsyncEngine (al startup)
  -> async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
  -> al request: AsyncSession via Depends
  -> al shutdown: engine.dispose()
```

EntrenadorAX implementa esto en [src/db/connection.py](../../../src/db/connection.py) y [src/main.py](../../../src/main.py).

## Engine: configuracion para produccion

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

engine = create_async_engine(
    settings.database_url,            # postgresql+asyncpg://user:pass@host:5432/db
    echo=False,                       # True solo en dev
    pool_size=10,                     # conexiones base (subir si hay >5 concurrent users tipicos)
    max_overflow=20,                  # burst capacity
    pool_timeout=10,                  # fail fast en lugar de colgar
    pool_pre_ping=True,               # health check antes de usar (catch stale connections)
    pool_recycle=300,                 # recyclar conexiones cada 5 min (evita timeout de PG)
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,           # CRITICO en async: evita MissingGreenlet
)
```

### Por que cada parametro

| Param | Por que importa |
|---|---|
| `expire_on_commit=False` | Evita que SQLAlchemy intente lazy-load atributos despues del commit (causaria MissingGreenlet en async) |
| `pool_pre_ping=True` | PostgreSQL puede cerrar conexiones inactivas; pre-ping detecta y reabre |
| `pool_recycle=300` | Evita conexiones que duran horas (PG default `idle_session_timeout`) |
| `pool_size` y `max_overflow` | Si los runs del agente IA duran 2-8s, el pool default de 5 se agota con 5 usuarios concurrentes |

### Connection string

```
postgresql+asyncpg://USER:PASS@HOST:PORT/DBNAME
```

NUNCA usar `postgresql://` (eso es psycopg2 sync). En Railway el `DATABASE_URL` viene como `postgresql://` y hay que convertirlo:

```python
url = settings.database_url
if url.startswith("postgresql://"):
    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
engine = create_async_engine(url, ...)
```

EntrenadorAX deberia agregar esta normalizacion si despliega en Railway sin que el usuario configure la URL manualmente.

## Lifespan (FastAPI)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()  # crea tablas si no existen
    logger.info("DB ready")

    yield

    # Shutdown
    await close_db()  # engine.dispose()

app = FastAPI(title="EntrenadorAX", lifespan=lifespan)
```

EntrenadorAX usa lifespan para inicializar tambien el `telegram_app`.

### Por que lifespan y no `@app.on_event("startup")`

`on_event` esta DEPRECADO desde FastAPI 0.93. Usar siempre `lifespan` para nuevo codigo.

## Session: patron Depends por-request

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

async def get_db():
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

@app.get("/usuario/{telegram_id}")
async def obtener_usuario(telegram_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Usuario).where(Usuario.telegram_id == telegram_id))
    return result.scalar_one_or_none()
```

### Regla critica para LLM endpoints

> Release the database session BEFORE long-running calls (e.g., LLM requests), not after.
> Evita mantener una conexion del pool ocupada 5-8 segundos mientras esperas la respuesta de OpenAI.

```python
# MAL: pool exhausted con pocos usuarios concurrentes
@app.post("/chat")
async def chat(msg: str, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(Usuario).where(...))
    result = await Runner.run(agent, msg)  # 5 segundos con conexion abierta!
    await db.commit()
    return result.final_output

# BIEN: usar sesion solo para queries, liberarla antes del LLM
@app.post("/chat")
async def chat(msg: str):
    async with async_session_factory() as db:
        user = await db.scalar(select(Usuario).where(...))
        # session se libera al salir del with

    # Aqui ya no tengo conexion del pool ocupada
    result = await Runner.run(agent, msg)

    async with async_session_factory() as db:
        # nueva sesion para persistir resultados
        await save_result(db, user.id, result)
        await db.commit()

    return result.final_output
```

Esto NO aplica a EntrenadorAX hoy porque el bot va por webhook directo, no Depends. Pero si se agrega API REST, importa.

## Repository pattern (lo que usa EntrenadorAX)

Centralizar queries en `src/db/repository.py`:

```python
# src/db/repository.py
from sqlalchemy import select
from src.db.connection import async_session_factory
from src.db.models import Usuario

async def obtener_o_crear_usuario(telegram_id: int, nombre: str | None = None) -> Usuario:
    async with async_session_factory() as session:
        result = await session.execute(select(Usuario).where(Usuario.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user is None:
            user = Usuario(telegram_id=telegram_id, nombre=nombre)
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user
```

Beneficios:
- Tests mas faciles (mockear repository)
- Toda la persistencia centralizada
- Las tools del SDK delegan al repository

## Queries SQLAlchemy 2.0 (estilo moderno)

```python
# Select uno
result = await session.execute(select(Usuario).where(Usuario.telegram_id == uid))
user = result.scalar_one_or_none()

# Select varios
result = await session.execute(select(Usuario).order_by(Usuario.created_at.desc()).limit(10))
users = list(result.scalars().all())

# Update
await session.execute(
    update(Usuario).where(Usuario.id == user_id).values(peso_kg=80)
)
await session.commit()

# Delete con relaciones cascadeantes
await session.execute(delete(Usuario).where(Usuario.id == user_id))
await session.commit()

# Aggregate
result = await session.execute(
    select(func.count(SesionEntrenamiento.id))
    .where(SesionEntrenamiento.usuario_id == user_id)
)
total = result.scalar()
```

NO usar el estilo viejo `session.query(Usuario).filter(...)` (deprecado en 2.0).

## Modelos con relaciones cascadeantes

```python
class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True)
    # ...
    sesiones = relationship(
        "SesionEntrenamiento",
        back_populates="usuario",
        cascade="all, delete-orphan",   # borrar usuario -> borrar sesiones
    )

class SesionEntrenamiento(Base):
    __tablename__ = "sesiones_entrenamiento"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    usuario = relationship("Usuario", back_populates="sesiones")
```

Ambos lados deben tener cascade: `relationship(..., cascade=...)` para ORM, `ForeignKey(..., ondelete="CASCADE")` para PostgreSQL.

## Migraciones

EntrenadorAX usa `Base.metadata.create_all` en `init_db()`. Esto es OK para prototipo, pero NO para produccion con cambios de schema.

Para produccion, agregar **Alembic**:

```bash
pip install alembic
alembic init alembic
# editar alembic/env.py para apuntar a engine async
alembic revision --autogenerate -m "agregar columna X"
alembic upgrade head
```

## Errores comunes

### MissingGreenlet
```
sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called
```
Causa: lazy-load de atributo despues de cerrar sesion (con `expire_on_commit=True`).
Fix: `expire_on_commit=False` en `async_sessionmaker` y/o eager-load con `selectinload()`.

### Too many clients
```
asyncpg.exceptions.TooManyConnectionsError
```
Causa: pool agotado por requests lentos (LLM) que mantienen conexion abierta.
Fix: liberar sesion antes del LLM (ver seccion arriba) o subir `pool_size`/`max_overflow`.

### Detached instance
```
DetachedInstanceError: Instance is not bound to a Session
```
Causa: usar `user.sesiones` despues de cerrar sesion (lazy load).
Fix: eager-load con `selectinload(Usuario.sesiones)` antes de cerrar.

### Driver mismatch
```
ImportError: greenlet is required for psycopg2 to work in asyncio
```
Causa: usaste `postgresql://` en lugar de `postgresql+asyncpg://`.

## Eager loading patterns

```python
from sqlalchemy.orm import selectinload, joinedload

# Trae usuario + todas sus sesiones en 2 queries
result = await session.execute(
    select(Usuario).options(selectinload(Usuario.sesiones))
)

# Trae usuario + sesiones + ejercicios anidados
result = await session.execute(
    select(Usuario).options(
        selectinload(Usuario.sesiones).selectinload(SesionEntrenamiento.ejercicios)
    )
)
```

`selectinload` (multi-query, mejor para colecciones) > `joinedload` (1 query con JOIN, mejor para uno-a-uno).

## Health check endpoint

EntrenadorAX expone `/health` simple. Mejorar con ping a DB:

```python
@app.get("/health")
async def health():
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok, "bot": telegram_app is not None}
```

## Performance tips

1. **Indexes**: agregar `index=True` en columnas que filtras con frecuencia (`telegram_id`, `fecha`).
2. **Batch inserts**: `session.add_all([obj1, obj2, ...])` + 1 `commit()`.
3. **No N+1**: usar `selectinload` para colecciones, `joinedload` para FK simples.
4. **Connection pool tuning**: monitorear `pool.status()` y ajustar `pool_size`.
5. **Async tasks fuera del pool**: si necesitas trabajo en background, usa `asyncio.create_task` PERO crea sesion nueva dentro (no reuses la del request).

## Testing

```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()

@pytest.mark.asyncio
async def test_crear_usuario(db_session):
    user = Usuario(telegram_id=123, nombre="Test")
    db_session.add(user)
    await db_session.commit()
    assert user.id is not None
```

Usar `sqlite+aiosqlite` en memoria para tests rapidos (sin Postgres real).
