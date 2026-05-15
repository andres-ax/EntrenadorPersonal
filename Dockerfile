FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .

# Instalar solo deps (sin el paquete local) para cachear la capa
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --no-deps -e . 2>/dev/null || true && \
    pip install --no-cache-dir \
    "openai-agents[redis]>=0.14" \
    "python-telegram-bot[job-queue]>=22.7" \
    "fastapi>=0.115" \
    "uvicorn[standard]>=0.34" \
    "asyncpg>=0.30" \
    "sqlalchemy[asyncio]>=2.0" \
    "pydantic-settings>=2.7" \
    "python-dotenv>=1.0"

COPY . .
RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
