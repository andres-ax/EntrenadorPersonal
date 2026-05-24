# DEPLOY.md - Deploy de EntrenadorAX

Deploy de EntrenadorAX en Railway con un solo servicio Python que sirve:
- bot Telegram
- panel admin HTML
- mini app HTML
- landing HTML
- WebSocket realtime
- APIs JSON

## Tabla de contenidos

1. [Servicios Railway](#servicios-railway)
2. [Setup inicial](#setup-inicial)
3. [Variables de entorno](#variables-de-entorno)
4. [Migraciones DB](#migraciones-db)
5. [Crear primer admin](#crear-primer-admin)
6. [Configurar webhook Telegram](#configurar-webhook-telegram)
7. [Endpoints públicos](#endpoints-publicos)
8. [Health checks](#health-checks)
9. [Wearables OAuth](#wearables-oauth)
10. [Cuentas de pago](#cuentas-de-pago)

---

## Servicios Railway

| Servicio | Rol | Dockerfile |
|---|---|---|
| `EntrenadorPersonal` | FastAPI + bot + admin HTML + mini app HTML + landing | `Dockerfile` |
| `Postgres` | Base de datos gestionada | Railway addon |
| `Redis` | cache / pubsub / sesiones gestionadas | Railway addon |

> Nota: el stack está consolidado en un único servicio FastAPI. Antes había servicios separados de realtime, worker y frontends en Cloudflare Pages.

## Setup inicial

1. Crear proyecto en Railway.
2. Añadir los addons `Postgres` y `Redis`.
3. Crear el servicio `EntrenadorPersonal` apuntando al repo y usando el `Dockerfile`.
4. Configurar las variables de entorno.

## Variables de entorno

Cargar al menos estas variables:

```env
TELEGRAM_TOKEN=...
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
JWT_SECRET=...
ADMIN_TOKEN=...
WEBHOOK_SECRET=...
FERNET_KEY=...
ENV=prod
```

Variables de URL:

```env
WEBHOOK_BASE_URL=https://entrenadorax.axsoftware.codes
MINIAPP_URL=https://entrenadorax.axsoftware.codes/app
LANDING_URL=https://entrenadorax.axsoftware.codes
ADMIN_URL=https://entrenadorax.axsoftware.codes/admin
```

Seed de admin inicial (solo primer deploy):

```env
ADMIN_SEED_EMAIL=entrenadorax@axsoftware.codes
ADMIN_SEED_PASSWORD=...
```

Precios opcionales:

```env
PRECIO_STARTER_COP=5000
PRECIO_PRO_COP=14990
PRECIO_ELITE_COP=39990
PRECIO_LIFETIME_COP=399000
```

Opcionales:

```env
SENTRY_DSN=...
PLAUSIBLE_DOMAIN=entrenadorax.axsoftware.codes
```

## Migraciones DB

Ejecutar migraciones manualmente:

```bash
railway run alembic upgrade head
```

> En producción, el contenedor también puede ejecutar migraciones al inicio si el script `start.sh` está configurado para ello.

## Crear primer admin

Si configuras `ADMIN_SEED_EMAIL` y `ADMIN_SEED_PASSWORD`, el admin se crea automáticamente en el primer arranque.

Alternativa manual:

```bash
railway run python scripts/crear_admin.py \
  --email tu@email.com \
  --password "tuPasswordSeguro" \
  --rol super
```

## Configurar webhook Telegram

El bot configura el webhook automáticamente al arrancar si `WEBHOOK_BASE_URL` está presente.

Si necesitas hacerlo manualmente:

```bash
curl -X POST "https://api.telegram.org/bot$TELEGRAM_TOKEN/setWebhook" \
  -d "url=https://entrenadorax.axsoftware.codes/webhook" \
  -d "secret_token=$WEBHOOK_SECRET" \
  -d 'allowed_updates=["message","callback_query","poll_answer","message_reaction","successful_payment","pre_checkout_query","inline_query"]'
```

Consultar la configuración actual del webhook:

```bash
curl https://entrenadorax.axsoftware.codes/webhook-info   -H "X-Admin-Token: $ADMIN_TOKEN"
```

## Endpoints publicos

- `/` -> landing HTML
- `/precios`, `/deportes`, `/deportes/{slug}`, `/politicas/*` -> landing
- `/sitemap.xml`, `/robots.txt` -> SEO
- `/admin/login` -> panel admin HTML
- `/admin/`, `/admin/usuarios`, `/admin/pagos`, etc. -> panel admin HTML
- `/admin/auth/login`, `/admin/usuarios`, ... -> API JSON (X-Admin-Token o JWT)
- `/app/dashboard`, `/app/llamar`, etc. -> mini app HTML (cookie `user_jwt`)
- `/api/me/*`, `/api/auth/*`, `/api/public/*`, `/api/integraciones/*` -> API JSON
- `/webhook` -> Telegram bot
- `/ws/realtime` -> WebSocket de voz
- `/health` -> healthcheck

## Cola de tareas Redis (operaciones)

Variables relevantes:

```env
USE_REDIS_TASK_QUEUE=true
TASK_DISPATCHER_INTERVAL_SECONDS=30
MAX_PROACTIVE_MSGS_PER_DAY=4
```

**Réplicas Railway:** mantener **una réplica** del servicio bot hasta verificar el lock
`entrenadorax:dispatcher:lock`. Escalar horizontalmente solo con lock probado.

**Runbook:**

| Problema | Acción |
|---------|--------|
| Spam proactivo a un usuario | `cancel_tasks(telegram_id)` vía admin o Redis CLI; revisar `task_audit_log` |
| Recordatorios duplicados | Verificar índice `uq_recordatorios_activos_dedup`; desactivar duplicados en Postgres |
| Tareas perdidas tras restart | Boot ejecuta `rehydrate_tasks_from_db()` en <60s |
| Sesión Redis corrupta | `/reset` o limpiar `agents:session:{uid}:*` |
| Cap diario | Key Redis `proactive_count:{uid}:{fecha}` TTL 48h |

Endpoints admin:

- `GET /admin/tasks/audit` — auditoría de tareas
- `GET /admin/metrics/proactivos?dias=7` — mensajes proactivos por usuario

Healthcheck incluye `tasks_overdue` (tareas vencidas en ZSET).

## Health checks

```bash
curl https://entrenadorax.axsoftware.codes/health
```

Ejemplo de respuesta:

```json
{"status":"ok","bot":true,"db":true,"redis":true,"db_pool":{...}}
```

## Wearables OAuth

Registrar redirect URI en cada portal de desarrollador:

- `https://entrenadorax.axsoftware.codes/api/integraciones/whoop/callback`
- `https://entrenadorax.axsoftware.codes/api/integraciones/strava/callback`
- `https://entrenadorax.axsoftware.codes/api/integraciones/garmin/callback`
- `https://entrenadorax.axsoftware.codes/api/integraciones/google_fit/callback`

Configurar estas variables en Railway:

- `WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET`
- `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`
- `GARMIN_CLIENT_ID`, `GARMIN_CLIENT_SECRET`
- `GOOGLE_FIT_CLIENT_ID`, `GOOGLE_FIT_CLIENT_SECRET`

## Cuentas de pago

- `CUENTA_DESTINO_PAGO` -> llave Bre-B principal
- `CUENTA_DESTINO_ALT` -> alternativa Bancolombia

---

## Notas adicionales

- Railway expone automáticamente el dominio `*.up.railway.app`.
- Si cambias el `WEBHOOK_BASE_URL`, reconfigura el webhook y reinicia el servicio.
- Asegúrate de que el contenedor use el `Dockerfile` correcto y que el servicio principal sea `EntrenadorPersonal`.
