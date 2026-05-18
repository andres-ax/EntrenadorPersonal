# =============================================================================
# Multi-stage build: stage 1 compila la landing Astro, stage 2 corre el bot.
# El bot-api sirve la landing estatica desde "/" para que la URL Railway
# muestre la home y NO un "Not Found".
# =============================================================================

# --- Stage 1: build de la landing (Astro) ---
FROM node:22-slim AS landing-builder

WORKDIR /landing

# Copia solo los manifests primero para aprovechar cache de Docker.
COPY frontend/landing/package.json frontend/landing/package-lock.json* ./
RUN npm install --no-audit --no-fund

# Copia el resto del proyecto landing y construye.
COPY frontend/landing/ .
RUN npm run build


# --- Stage 2: runtime Python (bot-api + landing servida estatica) ---
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

# Trae el dist/ generado por el stage 1 al directorio que el backend monta.
COPY --from=landing-builder /landing/dist /app/frontend/landing/dist

EXPOSE 8080

# El script ejecuta `alembic upgrade head` + `uvicorn` con $PORT correcto.
# Tambien lo usa Railway como startCommand (railway.toml apunta a ./start.sh).
RUN chmod +x /app/start.sh
CMD ["./start.sh"]
