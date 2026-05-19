# EntrenadorAX

EntrenadorAX es una plataforma de coaching deportivo integral basada en Telegram y OpenAI Agents.

La aplicación actual corre como un único servicio FastAPI que incluye:
- webhook de Telegram y bot polling local
- panel de administración HTML server-side
- panel de usuario / mini app HTML server-side
- landing pública y páginas de precios
- WebSocket de voz realtime para llamadas con el coach
- API JSON bajo `/api/*`
- almacenamiento en PostgreSQL y memoria en Redis

## Estructura principal

- `run_bot.py` — arranca el bot en modo polling para desarrollo local.
- `src/main.py` — arranca la app FastAPI con webhook, páginas HTML, APIs y realtime.
- `src/config.py` — carga todas las variables de entorno y valida la configuración.
- `src/coach.py` — define al agente `EntrenadorAX` y sus instrucciones.
- `src/tools.py` — expone las herramientas que el agente usa para leer/escribir datos.
- `src/db/` — conexión, modelos SQLAlchemy y repositorio de datos.
- `src/telegram/` — setup del bot, handlers, scheduler y pubsub.
- `src/api/` — rutas JSON para auth, usuarios, admin y integraciones.
- `src/web/` — rutas HTML server-side para landing, admin y app de usuario.
- `src/realtime/` — WebSocket de voz realtime.

## Dependencias principales

El proyecto usa:

- `openai-agents[redis]`
- `python-telegram-bot[job-queue]`
- `fastapi`
- `uvicorn[standard]`
- `asyncpg`
- `sqlalchemy[asyncio]`
- `alembic`
- `pydantic-settings`
- `python-dotenv`
- `redis`
- `matplotlib`
- `Pillow`

## Variables de entorno necesarias

Crea un archivo `.env` en la raíz con al menos estas variables:

```env
TELEGRAM_TOKEN=tu_token_de_telegram
OPENAI_API_KEY=tu_api_key_openai
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/entrenadorax
REDIS_URL=redis://localhost:6379/0
```

Opcionales importantes para producción o web:

```env
WEBHOOK_BASE_URL=https://tu-dominio.com
WEBHOOK_SECRET=secreto-webhook
ADMIN_TOKEN=secreto-admin
JWT_SECRET=secreto-jwt
MINIAPP_URL=https://mi-miniapp.com
LANDING_URL=https://mi-dominio.com
ADMIN_URL=https://mi-dominio.com
REALTIME_WS_URL=wss://mi-dominio.com/ws/realtime
```

## Cómo ejecutar en local

### 1. Modo polling (desarrollo Telegram directo)

```bash
python3 run_bot.py
```

Esto inicia el bot de Telegram en polling y no expone la app FastAPI.

### 2. Modo FastAPI / webhook

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Este modo arranca el servicio completo con:
- webhook de Telegram en `/webhook`
- healthcheck en `/health`
- webhook-info protegido en `/webhook-info`
- HTML landing en `/`, `/precios`, `/deportes`, `/politicas/*`
- admin UI en `/admin/*`
- panel de usuario en `/app/*`
- WebSocket de voz en `/ws/realtime`
- assets estáticos en `/static`

> Para probar webhook con Telegram desde local necesitas una URL pública como ngrok.

## Endpoints clave

### Telegram / webhook

- `GET /health` — estado de la app y readiness.
- `POST /webhook` — recibe actualizaciones de Telegram.
- `GET /webhook-info` — devuelve `webhook_url` y `secret_token`; requiere `X-Admin-Token`.
- `GET /sitemap.xml` — sitemap dinámico para SEO.
- `GET /robots.txt` — reglas de crawling para bots.

### Páginas HTML

- `/` — landing principal.
- `/precios` — página de precios.
- `/deportes` — listado de deportes.
- `/deportes/{slug}` — detalle de deporte.
- `/login` — login unificado para deportistas y admins.
- `/admin/*` — panel admin.
- `/app/*` — panel de usuario.

### WebSocket realtime

- `/ws/realtime` — WebSocket para llamadas de voz con el coach; requiere JWT.

### API JSON

- `/api/auth/*` — autenticación y códigos de login.
- `/api/me/*` — datos de usuario autenticado.
- `/api/admin/*` — endpoints admin JSON.
- `/api/public/*` — endpoints públicos.
- `/api/integraciones/*` — integraciones externas.

## Qué se puede probar en local

- Sí, puedes probar todo localmente.
- `run_bot.py` es ideal para pruebas rápidas de Telegram en polling.
- `uvicorn src.main:app` sirve la app completa en local.
- Para pruebas webhook reales desde Telegram, usa `ngrok` o un host público.

## Uso de Telegram

### Comandos core

- `/start`
- `/menu`
- `/hoy`
- `/entreno`
- `/comida`
- `/sueno`
- `/peso`
- `/reporte`
- `/pr`
- `/grafico`
- `/compromiso`
- `/tono`
- `/quiet_hours`
- `/pausa`
- `/dia_libre`
- `/ayuda`
- `/pagar`
- `/llamar`
- `/codigo_web`

### Comandos extra (español)

- `/mi_mes`
- `/historial_peso`
- `/firmar_compromiso`
- `/agua`
- `/calma`
- `/desafios`
- `/ranking`
- `/kudos`
- `/invitar`
- `/presumir`
- `/exportar_csv`
- `/apagar_firme`
- `/porque_me_escribiste`
- `/feedback`
- `/upgrade`
- `/planes`
- `/salir`
- `/reset`
- `/borrar_datos`

### Mini App / menú web

Si `MINIAPP_URL` está configurado, el bot publica un botón de menú que abre la mini app.

## Qué guarda la aplicación

- Perfil de usuario y onboarding.
- Entrenamientos y ejercicios.
- Comidas y macros.
- Sueño, horas y calidad.
- Peso y métricas corporales.
- Personal records (PRs).
- Sesiones y cuotas de voz realtime.

## Notas importantes

- `DATABASE_URL` y `REDIS_URL` son obligatorios.
- `TELEGRAM_TOKEN` y `OPENAI_API_KEY` son obligatorios.
- `WEBHOOK_BASE_URL` es necesario si usas webhook.
- `ADMIN_TOKEN` protege `/webhook-info` y endpoints admin.
- Todo corre en un solo proceso FastAPI: bot, web, APIs y realtime.

## Desarrollo local recomendado

1. `python3 -m venv .venv`
2. `source .venv/bin/activate`
3. `python3 -m pip install --upgrade pip`
4. `python3 -m pip install -e .`
5. `python3 -m uvicorn src.main:app --reload`

## Archivos clave para revisar

- `src/main.py`
- `src/telegram/bot_setup.py`
- `src/telegram/handlers.py`
- `src/web/landing.py`
- `src/web/admin_ui.py`
- `src/web/app_ui.py`
- `src/realtime/server.py`
- `src/config.py`

## Documentación adicional

- [ADMIN_GUIDE.md](ADMIN_GUIDE.md) — guía de administración y operación.
- [ENDPOINTS.md](ENDPOINTS.md) — referencia de webhook y API HTTP.
- [DEPLOY.md](DEPLOY.md) — guía de deploy en Railway.
- [PRICING_STRATEGY.md](PRICING_STRATEGY.md) — estrategia de precios y promociones.
- [INTERNAL_ARCHITECTURE.md](INTERNAL_ARCHITECTURE.md) — arquitectura interna y flujo del bot.
- [docs/diagrama_flujo.md](docs/diagrama_flujo.md) — diagrama de flujo del proceso.
