# Google Play Billing (Android app)

Guia para activar cobros reales cuando la cuenta Play Console este aprobada.
El codigo ya esta implementado con `GOOGLE_PLAY_BILLING_ENABLED=false` por defecto.

## 1. Completar cuenta Play Console

1. Verificar telefono en Play Console (pendiente mientras la cuenta esta en revision).
2. Completar ficha de la app y subir un **AAB** al track **Internal testing**.
3. Package name debe ser exactamente: `co.entrenadorax.app`.

## 2. Crear suscripciones (IDs exactos)

En **Monetizacion > Productos > Suscripciones**, crear:

| Product ID      | Plan backend | Periodo |
|-----------------|--------------|---------|
| `pro_mensual`   | pro          | mensual |
| `pro_anual`     | pro          | anual   |
| `elite_mensual` | elite        | mensual |
| `elite_anual`   | elite        | anual   |

Los IDs deben coincidir con [`src/services/google_play_products.py`](../src/services/google_play_products.py).

## 3. Service account (Android Publisher API)

1. En Google Cloud Console, crear service account.
2. Descargar JSON de credenciales.
3. En Play Console > Usuarios y permisos, invitar el service account con permiso **Ver datos financieros** y **Gestionar pedidos**.
4. En Railway (o `.env` local), setear:

```bash
GOOGLE_PLAY_BILLING_ENABLED=true
GOOGLE_PLAY_PACKAGE_NAME=co.entrenadorax.app
GOOGLE_PLAY_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'
```

Nunca commitear el JSON.

## 4. Real-Time Developer Notifications (RTDN)

1. Play Console > Monetizacion > Configuracion > Notificaciones en tiempo real.
2. Crear topic Pub/Sub en GCP.
3. Push subscription apuntando a:

```
https://entrenadorax.axsoftware.codes/api/webhooks/google-play/rtdn
```

4. Opcional: `GOOGLE_PLAY_RTDN_AUDIENCE` con la URL del webhook para validar JWT del push.

## 5. License testers

Play Console > Configuracion > License testing: agregar emails Gmail del equipo.

## 6. Migracion DB

En produccion:

```bash
alembic upgrade head
```

Aplica revision `0016_google_play_billing`.

## 7. Prueba E2E

1. Instalar build internal testing en dispositivo con cuenta tester.
2. Abrir app > Mas > Pagar.
3. Comprar Pro mensual.
4. Verificar:
   - Toast "Plan activado"
   - `/api/me/cuenta` devuelve `plan_actual=pro`, `billing_source=google_play`
   - Bot Telegram (si vinculado) respeta el mismo plan

## 8. Modo desarrollo (sin Play Console)

Con `ENV=dev` o `ENV=test` y billing deshabilitado, el backend acepta tokens de prueba:

```json
POST /api/me/billing/google/verify
{
  "purchase_token": "dev_pro_mensual_test001",
  "product_id": "pro_mensual"
}
```

Solo tokens con prefijo `dev_`.

## Archivos relevantes

| Componente | Ruta |
|------------|------|
| Productos / SKUs | `src/services/google_play_products.py` |
| Verificacion Google | `src/services/google_play_billing.py` |
| API verify/restore | `src/api/billing.py` |
| Android BillingClient | `EntrenadorAXFrontend/.../PlayBillingRepository.kt` |
| UI planes | `EntrenadorAXFrontend/.../PagarScreen.kt` |
