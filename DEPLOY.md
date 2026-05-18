# DEPLOY.md - Deploy de EntrenadorAX V2

Arquitectura multi-servicio en Railway + frontends estaticos en Cloudflare Pages.

## Servicios

| Servicio | Stack | Deploy | Puerto |
|---|---|---|---|
| `bot-api` | FastAPI + python-telegram-bot | Railway (Dockerfile) | 8000 |
| `realtime-ws` | FastAPI + WebSocket relay OpenAI | Railway (Dockerfile.realtime) | 8001 |
| `worker` | arq + asyncpg | Railway (Dockerfile.worker) | n/a |
| `admin-web` | Next.js 15 | Railway (frontend/admin/Dockerfile) | 3001 |
| `miniapp` | Vite + React | Cloudflare Pages (estatico) | - |
| `landing` | Astro 5 | Cloudflare Pages (estatico) | - |
| Postgres | managed | Railway addon | 5432 |
| Redis | managed | Railway addon | 6379 |

## Setup inicial Railway

1. Crear proyecto en Railway.
2. Anadir addons: Postgres + Redis.
3. Crear 4 servicios:
   - `bot-api` -> apunta al repo, usa `Dockerfile`
   - `realtime-ws` -> mismo repo, usa `Dockerfile.realtime`
   - `worker` -> mismo repo, usa `Dockerfile.worker`
   - `admin-web` -> mismo repo, root path `frontend/admin/`, usa `Dockerfile`

4. Setea variables compartidas (mismo Postgres y Redis en los 4):
   - `DATABASE_URL` -> referencia a la DB de Railway
   - `REDIS_URL` -> referencia al Redis de Railway
   - `TELEGRAM_TOKEN`, `OPENAI_API_KEY`, `JWT_SECRET`, `ADMIN_TOKEN`, `WEBHOOK_SECRET`, `FERNET_KEY`
   - `MINIAPP_URL`, `LANDING_URL`, `ADMIN_URL`, `REALTIME_WS_URL`

5. Variables especificas:
   - `admin-web`: `NEXT_PUBLIC_API_BASE_URL` = URL publica del bot-api
   - `realtime-ws`: solo necesita las compartidas

## Frontends Cloudflare Pages

```bash
cd frontend/miniapp
npm install && npm run build
wrangler pages deploy dist --project-name entrenadorax-miniapp

cd ../landing
npm install && npm run build
wrangler pages deploy dist --project-name entrenadorax-landing
```

Asigna dominios en Cloudflare:
- `app.entrenadorax.com` -> miniapp
- `entrenadorax.com` -> landing
- `admin.entrenadorax.com` -> admin-web Railway (CNAME a railway.app)

## Migraciones DB

Una vez deployed, ejecuta en bot-api:

```bash
railway run alembic upgrade head
```

## Crear primer admin

```bash
railway run python scripts/crear_admin.py \
  --email tu@email.com --password "tuPasswordSeguro" --rol super
```

## Configurar webhook Telegram

```bash
# Obtener el secret token del bot-api
curl https://api.entrenadorax.com/webhook-info \
  -H "X-Admin-Token: $ADMIN_TOKEN"

# Setear webhook en Telegram
curl -X POST "https://api.telegram.org/bot$TELEGRAM_TOKEN/setWebhook" \
  -d "url=https://api.entrenadorax.com/webhook" \
  -d "secret_token=$WEBHOOK_SECRET" \
  -d "allowed_updates=[\"message\",\"callback_query\",\"poll_answer\",\"message_reaction\",\"successful_payment\",\"pre_checkout_query\",\"inline_query\"]"
```

## Health checks

- `https://api.entrenadorax.com/health` -> bot-api (DB + Redis + bot)
- `https://realtime.entrenadorax.com/health` -> realtime-ws
- `https://admin.entrenadorax.com/login` -> admin-web

## Migracion v1 -> v2

```bash
# 1. Backup DB
railway run pg_dump $DATABASE_URL > backup_v1.sql

# 2. Aplicar migraciones nuevas
railway run alembic upgrade head

# 3. Migrar suscripciones existentes a tiers
railway run python scripts/migrar_suscripciones_a_tiers.py             # dry-run
railway run python scripts/migrar_suscripciones_a_tiers.py --apply    # ejecuta
```

## Setear menu button Mini App

Tras setear `MINIAPP_URL`, reinicia el bot-api. El `post_init` registra
automaticamente `setChatMenuButton` apuntando a la Mini App.

## Wearables OAuth setup

Para cada proveedor, registra app en su developer portal:

- Whoop: redirect URI = `https://api.entrenadorax.com/api/integraciones/whoop/callback`
- Strava: idem
- Garmin: idem
- Google Fit: idem

Setea `<PROVEEDOR>_CLIENT_ID` y `<PROVEEDOR>_CLIENT_SECRET` en bot-api y worker.

## Cuentas de pago

Crea cuentas Bre-B / Nequi / Daviplata empresariales:
- `CUENTA_DESTINO_PAGO` -> llave Bre-B principal (ej: 300 123 4567)
- `CUENTA_DESTINO_ALT` -> alternativa Bancolombia
