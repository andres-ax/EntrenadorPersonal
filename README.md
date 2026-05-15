# EntrenadorAX

EntrenadorAX es una aplicación de coaching deportivo personal basada en Telegram y OpenAI Agents.

## Flujo de trabajo general

```mermaid
graph TD
    A["Configurar .env"] --> B["Elegir modo de ejecución"]
    B --> C["run_bot.py (polling)"]
    B --> D["FastAPI webhook"]
    C --> E["Telegram recibe mensaje"]
    D --> E
    E --> F["Handlers / Prompt builder"]
    F --> G["Ejecutar agente EntrenadorAX"]
    G --> H["Tool call: registro / consulta"]
    H --> I["Base de datos PostgreSQL"]
    H --> J["Redis sesión + rate limit"]
    G --> K["Respuesta al usuario"]
```

## Qué hace esta aplicación

- Es un bot de Telegram que conversa con el usuario en español.
- Gestiona onboarding de perfil, entrenamientos, comidas, sueño y peso.
- Guarda datos en una base de datos PostgreSQL asíncrona.
- Usa Redis para memoria de conversación y límite de tasa.
- Envía recordatorios automáticos diarios y semanales.

## Estructura principal

- `run_bot.py` - arranca el bot en modo polling (desarrollo local).
- `src/main.py` - arranca la app FastAPI para webhook de Telegram.
- `src/config.py` - carga variables desde `.env`.
- `src/coach.py` - define al agente `EntrenadorAX` y sus reglas.
- `src/tools.py` - define las herramientas (`tools`) que el agente puede usar.
- `src/db/` - contiene la conexión, modelos y repositorio de datos.
- `src/telegram/` - define handlers, middleware de rate limit y scheduler de recordatorios.

## Dependencias principales

El proyecto usa:

- `openai-agents[redis]`
- `python-telegram-bot[job-queue]`
- `fastapi`
- `uvicorn[standard]`
- `asyncpg`
- `sqlalchemy[asyncio]`
- `pydantic-settings`
- `python-dotenv`

## Instalar y ejecutar

Para ejecutar la aplicación localmente, usa `INSTALL.md` que ya está en el proyecto.

### Resumen rápido de ejecución

1. Crea un entorno virtual:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. Instala dependencias:
   ```bash
   python3 -m pip install --upgrade pip
   python3 -m pip install -e .
   ```
3. Crea `.env` en la raíz con estas variables:
   ```env
   TELEGRAM_TOKEN=tu_token_de_telegram
   DATABASE_URL=postgresql+asyncpg://user:pass@localhost/dbname
   REDIS_URL=redis://localhost:6379/0
   OPENAI_API_KEY=tu_api_key_openai
   WEBHOOK_BASE_URL=https://tu-dominio.com
   ```
4. Ejecuta el bot en polling:
   ```bash
   python3 run_bot.py
   ```

### Alternativa webhook

Para ejecutar la app en modo webhook:

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Luego configura el webhook de Telegram usando el `secret_token` que devuelve `/webhook-info`.

## Uso del bot en Telegram

### Comandos disponibles

- `/start` - iniciar conversación y onboarding.
- `/menu` - muestra botones rápidos para registrar entreno, comida, sueño, peso y ver reportes.
- `/reset` - reinicia la sesión conversacional en Redis.
- `/borrar_datos` - elimina permanentemente todos los datos del usuario.

### Botones del menú

- Registrar entreno
- Registrar comida
- Como dormí
- Mi peso actual
- Reporte semanal
- Historial de peso

### Flujo principal

- Si el usuario no tiene perfil completo, el bot hace onboarding conversacional.
- Si ya está onboarded, el bot propone entrenamientos, pide registros y envía recordatorios.
- Los datos se guardan automáticamente en la base de datos.

## Qué datos guarda

- Perfil: nombre, edad, peso, altura, objetivo, nivel, días de entrenamiento, deporte principal.
- Entrenamientos: tipo, duración, ejercicios, RPE, notas.
- Comidas: tipo, alimentos, calorías y macros.
- Sueño: horas, calidad, notas.
- Peso y métricas corporales.
- Personal records (PRs).

## Endpoints web

Si usas webhook, la app expone:

- `GET /health` - estado de la app.
- `POST /webhook` - recibe actualizaciones de Telegram.
- `GET /webhook-info` - muestra la URL y secreto para configurar el webhook.

## Deployment

El `Dockerfile` ya está preparado para ejecutar la app con `uvicorn src.main:app`.

## Notas importantes

- La configuración principal se carga desde `.env`.
- Redis es necesario para la memoria del agente y el rate limit.
- PostgreSQL es necesario para almacenar perfiles y registros.

---

Para más detalles técnicos, revisa `src/coach.py`, `src/tools.py`, `src/telegram/handlers.py` y `src/telegram/scheduler.py`.
