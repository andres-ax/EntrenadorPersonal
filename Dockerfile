# =============================================================================
# Dockerfile single-stage Python puro.
#
# Antes: multi-stage con Node 22 que compilaba la landing Astro -> dist/.
# Ahora: la landing, el admin y la mini app son templates Jinja2 servidos
# directamente por FastAPI. Cero Node, cero TypeScript, cero build step
# de frontend. Build ~3x mas rapido y un unico stack en el repo.
# =============================================================================
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir -e . --no-deps

EXPOSE 8080

# start.sh corre `alembic upgrade head` + `uvicorn` con $PORT correcto.
# Railway lo usa como startCommand (railway.toml apunta a ./start.sh).
RUN chmod +x /app/start.sh
CMD ["./start.sh"]
