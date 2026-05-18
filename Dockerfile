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

# El script ejecuta `alembic upgrade head` + `uvicorn` con $PORT correcto.
# Tambien lo usa Railway como startCommand (railway.toml apunta a ./start.sh).
RUN chmod +x /app/start.sh
CMD ["./start.sh"]
