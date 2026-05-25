"""Fixtures comunes. Setea env vars dummy antes de importar src."""
from __future__ import annotations

import os
os.environ.setdefault("TELEGRAM_TOKEN", "123:test-token-fake")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENV", "test")

import asyncio
import json
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Configuración del motor y la sesión SQLite de test
DB_FILE = "test_temp_db.sqlite"
if os.path.exists(DB_FILE):
    try:
        os.remove(DB_FILE)
    except Exception:
        pass

test_engine = create_async_engine(f"sqlite+aiosqlite:///{DB_FILE}", echo=False)
test_session_factory = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Patching inmediato del módulo db connection antes de que otros módulos carguen
import src.db.connection
src.db.connection.async_session_factory = test_session_factory
src.db.connection.engine = test_engine

# Crear todas las tablas en SQLite al inicio de la sesión
async def _init_tables():
    import src.db.models
    from src.db.models import Base
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

asyncio.run(_init_tables())


class MockRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = str(value)

    async def setex(self, key, seconds, value):
        self.store[key] = str(value)

    async def delete(self, *keys):
        for key in keys:
            self.store.pop(key, None)


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def db_session():
    async with test_session_factory() as session:
        yield session
        # Limpiar datos de las tablas después de cada test
        from src.db.models import Base
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()


@pytest_asyncio.fixture
async def mock_redis():
    return MockRedis()


@pytest_asyncio.fixture
async def api_client(mock_redis, monkeypatch):
    async def get_mock_redis():
        return mock_redis

    monkeypatch.setattr("src.cache.get_redis", get_mock_redis)

    from src.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def call_tool(tool, **kwargs) -> str:
    """Helper para invocar tools @function_tool en tests.

    Construye un ToolContext minimal y serializa kwargs a JSON.
    Devuelve el output crudo (string JSON o mensaje de error).
    """
    from agents.tool_context import ToolContext

    ctx = ToolContext(
        context=None,
        tool_name=tool.name,
        tool_call_id="test-call-id",
        tool_arguments=json.dumps(kwargs),
    )
    return await tool.on_invoke_tool(ctx, json.dumps(kwargs))
