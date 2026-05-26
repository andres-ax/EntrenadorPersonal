# ENDPOINTS.md - Endpoints de EntrenadorAX

Este archivo describe los endpoints HTTP expuestos por la app en modo webhook. Incluye ejemplos de Postman, cURL y notas de uso.

> Estos endpoints están disponibles solo cuando se ejecuta con FastAPI:
>
> ```bash
> uvicorn src.main:app --host 0.0.0.0 --port 8000
> ```
>
> Si usas `python3 run_bot.py`, el bot corre en polling y no expone estos endpoints.

## Tabla de contenidos

1. [GET /health](#1-get-health)
2. [GET /webhook-info](#2-get-webhook-info)
3. [POST /webhook](#3-post-webhook)
4. [Configurar Telegram para el webhook](#4-configurar-telegram-para-el-webhook)
5. [Probar en local con ngrok](#5-probar-en-local-con-ngrok)
6. [Nota sobre polling vs webhook](#6-nota-sobre-polling-vs-webhook)
7. [API Chat multicanal (Android)](#7-api-chat-multicanal-android)
8. [WebSocket Realtime](#8-websocket-realtime)

## 1. GET /health

Comprueba si la app está activa y si el bot está inicializado.

- URL: `http://localhost:8000/health`
- Método: `GET`

### Ejemplo cURL

```bash
curl http://localhost:8000/health
```

### Respuesta esperada

```json
{
  "status": "ok",
  "bot": true
}
```

## 2. GET /webhook-info

Devuelve la URL del webhook y el secret token para Telegram.

- URL: `http://localhost:8000/webhook-info`
- Método: `GET`

### Ejemplo cURL

```bash
curl http://localhost:8000/webhook-info
```

### Respuesta esperada

```json
{
  "webhook_url": "https://tu-dominio.com/webhook",
  "secret_token": "...secret...",
  "note": "Usa: curl -X POST 'https://api.telegram.org/bot<TOKEN>/setWebhook?url=<webhook_url>&secret_token=<secret_token>'"
}
```

> `webhook_url` depende de `WEBHOOK_BASE_URL` en `.env`.

## 3. POST /webhook

Recibe actualizaciones de Telegram y las envía al bot.

- URL: `http://localhost:8000/webhook`
- Método: `POST`
- Headers:
  - `Content-Type: application/json`
  - `x-telegram-bot-api-secret-token: <secret_token>`

### Ejemplo cURL

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "x-telegram-bot-api-secret-token: <secret_token>" \
  -d '{"update_id":123456789,"message":{"message_id":1,"from":{"id":123456789,"is_bot":false,"first_name":"Diego","username":"diego123","language_code":"es"},"chat":{"id":123456789,"first_name":"Diego","username":"diego123","type":"private"},"date":1710470400,"text":"Hola"}}'
```

### Respuesta esperada

```json
{
  "ok": true
}
```

> Si el header `x-telegram-bot-api-secret-token` es incorrecto, la respuesta es `403`.

## 4. Configurar Telegram para el webhook

Después de arrancar la app con FastAPI y obtener `secret_token` de `/webhook-info`, ejecuta:

```bash
curl -X POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/setWebhook?url=https://tu-dominio.com/webhook&secret_token=<secret_token>"
```

- `TELEGRAM_TOKEN`: token del bot.
- `https://tu-dominio.com/webhook`: URL pública accesible desde Internet.
- `secret_token`: valor de `/webhook-info`.

## 5. Probar en local con ngrok

1. Arranca la app FastAPI:
   ```bash
   uvicorn src.main:app --host 0.0.0.0 --port 8000
   ```
2. Expón el puerto con ngrok:
   ```bash
   ngrok http 8000
   ```
3. Usa la URL pública de ngrok en `WEBHOOK_BASE_URL` o configura el webhook con esa URL.

## 6. Nota sobre polling vs webhook

- `POST /webhook` es útil para probar el endpoint HTTP.
- En modo polling (`python3 run_bot.py`) no hay endpoint HTTP de recepción de mensajes.
- Para probar la experiencia completa, usa el bot en Telegram y webhook con FastAPI.

## 7. API Chat multicanal (Android)

Todos requieren `Authorization: Bearer <JWT>` (mismo token de la app).

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| GET | `/api/me/conversaciones` | Lista hilos |
| POST | `/api/me/conversaciones` | Crear hilo `{titulo?}` |
| PATCH | `/api/me/conversaciones/{id}` | Renombrar / archivar |
| GET | `/api/me/conversaciones/{id}/mensajes` | Historial `?before=&limit=` |
| POST | `/api/me/conversaciones/{id}/chat` | Chat texto sync `{mensaje}` |
| POST | `/api/me/conversaciones/{id}/chat/stream` | SSE (respuesta completa) |
| POST | `/api/me/conversaciones/{id}/audio` | multipart `file` → Whisper |
| POST | `/api/me/conversaciones/{id}/handoff/telegram` | Resumen + mensaje bot |
| POST | `/api/me/conversaciones/activa` | `{conversacion_id}` hilo activo |
| GET | `/api/me/realtime/cuota` | Minutos de voz disponibles |

### Ejemplo chat texto

```bash
curl -X POST "https://entrenadorax.axsoftware.codes/api/me/conversaciones/1/chat" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"mensaje":"Que toca hoy?"}'
```

### Feature flags (.env)

- `CHAT_ANDROID_ENABLED=true`
- `CHAT_MULTITHREAD_ENABLED=true`
- `CHAT_HANDOFF_ENABLED=true`

## 8. WebSocket Realtime

- URL: `wss://entrenadorax.axsoftware.codes/ws/realtime?token=<JWT>`
- Audio cliente → servidor: bytes PCM16 24kHz mono
- Audio servidor → cliente: bytes PCM16
- Eventos JSON: `cuota`, `transcript`, `error` (`sin_cuota`)
- Cierre: enviar `{"type":"fin"}`
