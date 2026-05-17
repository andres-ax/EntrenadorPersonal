"""Fixtures comunes. Setea env vars dummy antes de importar src."""
import os

os.environ.setdefault("TELEGRAM_TOKEN", "123:test-token-fake")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENV", "test")
