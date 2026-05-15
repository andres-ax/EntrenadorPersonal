# Endpoints de EntrenadorAX

Este archivo describe los endpoints HTTP expuestos por la aplicación en modo webhook, con ejemplos para Postman y cURL.

> Nota: estos endpoints solo están disponibles cuando se ejecuta la app con FastAPI:
>
> ```bash
> uvicorn src.main:app --host 0.0.0.0 --port 8000
> ```
>
> Si ejecutas `python3 run_bot.py`, el bot funciona en polling y no expone estos endpoints.

## 1. GET /health

Comprueba si la app está activa y si el bot está inicializado.

- URL: `http://localhost:8000/health`
- Método: `GET`

### Ejemplo Postman

- Método: GET
- URL: `http://localhost:8000/health`

### Respuesta esperada

```json
{
  "status": "ok",
  "bot": true
}
```


## 2. GET /webhook-info

Devuelve la URL del webhook y el secret token que debes usar al configurar Telegram.

- URL: `http://localhost:8000/webhook-info`
- Método: `GET`

### Ejemplo Postman

- Método: GET
- URL: `http://localhost:8000/webhook-info`

### Respuesta esperada

```json
{
  "webhook_url": "https://tu-dominio.com/webhook",
  "secret_token": "...secret...",
  "note": "Usa: curl -X POST 'https://api.telegram.org/bot<TOKEN>/setWebhook?url=<webhook_url>&secret_token=<secret_token>'"
}
```

> El valor de `webhook_url` depende de `WEBHOOK_BASE_URL` en tu `.env`.

## 3. POST /webhook

Recibe actualizaciones de Telegram y las envía al bot.

- URL: `http://localhost:8000/webhook`
- Método: `POST`
- Encabezados:
  - `Content-Type: application/json`
  - `x-telegram-bot-api-secret-token: <secret_token>`

### Ejemplo Postman

1. Método: POST
2. URL: `http://localhost:8000/webhook`
3. Headers:
   - `Content-Type`: `application/json`
   - `x-telegram-bot-api-secret-token`: copia el valor de `secret_token` de `/webhook-info`
4. Body: raw JSON

### Ejemplo de body de Telegram update

```json
{
  "update_id": 123456789,
  "message": {
    "message_id": 1,
    "from": {
      "id": 123456789,
      "is_bot": false,
      "first_name": "Diego",
      "username": "diego123",
      "language_code": "es"
    },
    "chat": {
      "id": 123456789,
      "first_name": "Diego",
      "username": "diego123",
      "type": "private"
    },
    "date": 1710470400,
    "text": "Hola"
  }
}
```

### Respuesta esperada

```json
{
  "ok": true
}
```

> Si el header `x-telegram-bot-api-secret-token` es incorrecto, recibes un `403`.

## 4. Cómo configurar Telegram para usar el webhook

Después de arrancar la app con FastAPI y obtener el secret token en `/webhook-info`, configura Telegram con:

```bash
curl -X POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/setWebhook?url=https://tu-dominio.com/webhook&secret_token=<secret_token>"
```

- `TELEGRAM_TOKEN` es tu token del bot.
- `https://tu-dominio.com/webhook` debe ser accesible desde internet.
- `secret_token` debe coincidir con el valor devuelto en `/webhook-info`.

## 5. Prueba en local usando herramientas como ngrok

Si estás desarrollando localmente y quieres probar con Telegram real:

1. Arranca la app FastAPI:
   ```bash
   uvicorn src.main:app --host 0.0.0.0 --port 8000
   ```
2. Exponerla con ngrok:
   ```bash
   ngrok http 8000
   ```
3. Usa la URL pública de ngrok en `WEBHOOK_BASE_URL` o configura el webhook con esa URL.

## 6. Nota sobre Postman y el bot en polling

- `POST /webhook` es útil para probar el endpoint HTTP del bot.
- Para probar la lógica real de Telegram en modo polling debes usar el bot en Telegram y `python3 run_bot.py`.
- En modo polling no puedes enviar mensajes desde Postman al bot, porque no existe endpoint HTTP para recibirlos.
