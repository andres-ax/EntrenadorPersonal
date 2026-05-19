"""Fixtures comunes. Setea env vars dummy antes de importar src."""

import json
import os

os.environ.setdefault("TELEGRAM_TOKEN", "123:test-token-fake")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENV", "test")


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
