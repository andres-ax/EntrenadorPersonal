# DEPLOY.md - Deploy de EntrenadorAX

Stack consolidado: **un solo proceso Python en Railway** que sirve el bot,
el admin panel, la mini app y la landing. Cero servicios extra.

## Servicios Railway

| Servicio | Rol | Dockerfile |
|---|---|---|
| `EntrenadorPersonal` | FastAPI + bot + admin HTML + mini app HTML + landing | `Dockerfile` |
| `Postgres` | DB managed | (Railway addon) |
| `Redis` | cache / pubsub / sesiones managed | (Railway addon) |

> Antes existian servicios separados `realtime-ws`, `worker`,
> `entrenadorax-admin`, y frontends en Cloudflare Pages (Astro / Vite /
> Next.js). Todos consolidados en el unico FastAPI con templates Jinja2.

## Setup inicial Railway

1. Crear proyecto en Railway.
2. Anadir addons: Postgres + Redis.
3. Crear servicio `EntrenadorPersonal` apuntando al repo (usa `Dockerfile`).
4. Setear variables (las mas importantes):

```
TELEGRAM_TOKEN=...
OPENAI_API_KEY=sk-proj-...
DATABASE_URL=postgresql://...   # Railway lo da automatico si haces ref
REDIS_URL=redis://...           # idem
JWT_SECRET=...                  # python3 -c "import secrets; print(secrets.token_urlsafe(48))"
ADMIN_TOKEN=...                 # idem
WEBHOOK_SECRET=...              # openssl rand -hex 32
FERNET_KEY=...                  # Fernet.generate_key().decode()
ENV=prod

# URLs (Railway expone *.up.railway.app automaticamente)
WEBHOOK_BASE_URL=https://entrenadorax.axsoftware.codes
MINIAPP_URL=https://entrenadorax.axsoftware.codes/app
LANDING_URL=https://entrenadorax.axsoftware.codes
ADMIN_URL=https://entrenadorax.axsoftware.codes/admin

# Seed del primer admin (solo en primer deploy)
ADMIN_SEED_EMAIL=entrenadorax@axsoftware.codes
ADMIN_SEED_PASSWORD=...

# Pricing
PRECIO_STARTER_COP=5000
PRECIO_PRO_COP=14990
PRECIO_ELITE_COP=39990
PRECIO_LIFETIME_COP=399000

# Opcional: Sentry / Plausible
SENTRY_DSN=...
PLAUSIBLE_DOMAIN=entrenadorax.axsoftware.codes
```

## Migraciones DB

```bash
railway run alembic upgrade head
```

Tambien corren automaticamente al arrancar el contenedor (`start.sh`).

## Crear primer admin

Si seteas `ADMIN_SEED_EMAIL` + `ADMIN_SEED_PASSWORD`, el bot crea el admin
en el primer arranque (idempotente). Alternativa manual:

```bash
railway run python scripts/crear_admin.py \
  --email tu@email.com --password "tuPasswordSeguro" --rol super
```

## Configurar webhook Telegram

El bot setea el webhook automaticamente al arrancar si `WEBHOOK_BASE_URL`
esta configurado. Si necesitas hacerlo manualmente:

```bash
curl -X POST "https://api.telegram.org/bot$TELEGRAM_TOKEN/setWebhook" \
  -d "url=https://entrenadorax.axsoftware.codes/webhook" \
  -d "secret_token=$WEBHOOK_SECRET" \
  -d "allowed_updates=[\"message\",\"callback_query\",\"poll_answer\",\"message_reaction\",\"successful_payment\",\"pre_checkout_query\",\"inline_query\"]"
```

Inspeccionar config actual:

```bash
curl https://entrenadorax.axsoftware.codes/webhook-info \
  -H "X-Admin-Token: $ADMIN_TOKEN"
```

## Endpoints publicos del servicio unico

- `/` -> landing HTML
- `/precios`, `/deportes`, `/deportes/{slug}`, `/politicas/*` -> landing
- `/sitemap.xml`, `/robots.txt` -> SEO
- `/admin/login` -> panel HTML (Jinja2)
- `/admin/`, `/admin/usuarios`, `/admin/pagos`, etc. -> panel HTML
- `/admin/auth/login`, `/admin/usuarios`, ... -> JSON API (X-Admin-Token o JWT)
- `/app/dashboard`, `/app/llamar`, etc. -> mini app HTML (cookie user_jwt)
- `/api/me/*`, `/api/auth/*`, `/api/public/*`, `/api/integraciones/*` -> JSON API
- `/webhook` -> Telegram bot
- `/ws/realtime` -> WebSocket llamada de voz
- `/health` -> healthcheck

## Health checks

```bash
curl https://entrenadorax.axsoftware.codes/health
# {"status":"ok","bot":true,"db":true,"redis":true,"db_pool":{...}}
```

## Wearables OAuth

Registrar redirect URI en cada developer portal:
- `https://entrenadorax.axsoftware.codes/api/integraciones/{whoop|strava|garmin|google_fit}/callback`

Setear `<PROVEEDOR>_CLIENT_ID` y `<PROVEEDOR>_CLIENT_SECRET` en el servicio.

## Cuentas de pago

- `CUENTA_DESTINO_PAGO` -> llave Bre-B principal
- `CUENTA_DESTINO_ALT` -> alternativa Bancolombia
