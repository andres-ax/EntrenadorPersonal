#!/bin/sh
# Entrypoint para Railway (bot-api).
# Ejecuta migraciones Alembic y arranca FastAPI/uvicorn en el $PORT que
# Railway inyecta (default 8080 para dev local).
set -e

echo "[start.sh] ENV=${ENV:-dev} | PORT=${PORT:-8080}"
echo "[start.sh] Aplicando migraciones Alembic..."
alembic upgrade head
echo "[start.sh] Migraciones OK. Arrancando uvicorn..."

exec uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8080}"
