---
name: python-telegram-bot-v22
description: Patrones actualizados de python-telegram-bot v22.7+ con job-queue para EntrenadorAX. Cubre Application builder, webhook vs polling, CommandHandler/MessageHandler/CallbackQueryHandler, JobQueue diaria/semanal, error handler global, manejo de TimedOut/RetryAfter, send_action typing. Use proactively al editar src/telegram/handlers.py, src/telegram/scheduler.py, src/main.py o run_bot.py, al agregar comandos nuevos, jobs programados, o cambiar entre webhook y polling.
---

# python-telegram-bot v22

Doc oficial v22.7: https://docs.python-telegram-bot.org/en/v22.7/

Cliente async oficial de Telegram para Python. EntrenadorAX usa el extra `[job-queue]` que agrega APScheduler para recordatorios.

## Componentes que usa EntrenadorAX

| Componente | Uso |
|---|---|
| `Application` | Coordinador principal del bot |
| `ApplicationBuilder` | Construye la app con token y config |
| `CommandHandler` | `/start`, `/menu`, `/reset`, `/borrar_datos` |
| `MessageHandler(filters.TEXT)` | Mensajes de texto del usuario |
| `CallbackQueryHandler` | Botones inline |
| `JobQueue` | Recordatorios diarios/semanales (APScheduler) |
| `Application.add_error_handler` | Captura excepciones globales |

## Construccion basica

### Modo polling (desarrollo local: `run_bot.py`)

```python
from telegram.ext import Application

app = Application.builder().token(settings.telegram_token).build()
registrar(app)            # handlers
registrar_jobs(app)       # jobs APScheduler
app.add_error_handler(error_handler)

await app.initialize()
await app.start()
await app.updater.start_polling(drop_pending_updates=True)
# ... mantener vivo
await app.updater.stop()
await app.stop()
await app.shutdown()
```

### Modo webhook (produccion Railway: `src/main.py`)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app
    telegram_app = Application.builder().token(settings.telegram_token).build()
    registrar(telegram_app)
    await telegram_app.initialize()
    await telegram_app.start()
    yield
    await telegram_app.stop()
    await telegram_app.shutdown()
```

El endpoint `/webhook` recibe el POST de Telegram y llama `telegram_app.process_update(update)`.

## Reglas duras

1. **NUNCA mezclar polling y webhook**: borra el webhook antes de polling y viceversa.
2. **Validar `X-Telegram-Bot-Api-Secret-Token`** en webhook endpoint (ya implementado en EntrenadorAX con `WEBHOOK_SECRET`).
3. **Siempre `await app.initialize()` antes de `start()`** y `shutdown()` despues de `stop()`.
4. **`drop_pending_updates=True` en polling** para evitar procesar mensajes acumulados al iniciar.
5. **Retry con backoff exponencial** ante `telegram.error.TimedOut` y respetar `RetryAfter.retry_after`.
6. **NUNCA enviar mensaje > 4096 chars** sin chunking (Telegram lo rechaza).
7. **Usar `send_action("typing")`** antes de operaciones lentas (LLM) para feedback al usuario.

## Patron de envio con retry (EntrenadorAX-style)

```python
import asyncio
import telegram.error

async def _enviar_con_retry(message, texto: str, intentos: int = 3):
    for i in range(intentos):
        try:
            await message.reply_text(texto)
            return
        except telegram.error.TimedOut:
            if i == intentos - 1:
                raise
            await asyncio.sleep(1.5 ** i)
        except telegram.error.RetryAfter as e:
            await asyncio.sleep(e.retry_after)
            if i == intentos - 1:
                raise
```

Ya implementado en [src/telegram/handlers.py](../../../src/telegram/handlers.py).

## Chunking de mensajes largos

```python
output = result.final_output
for i in range(0, len(output), 4000):
    await _enviar_con_retry(message, output[i:i + 4000])
```

4000 (no 4096) para dar margen ante caracteres especiales.

## Handlers tipicos

### CommandHandler

```python
from telegram.ext import CommandHandler

async def start(update, ctx):
    uid = update.effective_user.id
    await update.message.reply_text("Hola!")

app.add_handler(CommandHandler("start", start))
```

### MessageHandler con filtros

```python
from telegram.ext import MessageHandler, filters

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensaje))
# Filtros utiles: filters.PHOTO, filters.VOICE, filters.LOCATION, filters.Document.PDF
```

### CallbackQueryHandler (botones inline)

```python
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler

async def menu(update, ctx):
    keyboard = [
        [InlineKeyboardButton("Opcion A", callback_data="opt_a")],
        [InlineKeyboardButton("Opcion B", callback_data="opt_b")],
    ]
    await update.message.reply_text("Elige:", reply_markup=InlineKeyboardMarkup(keyboard))

async def boton(update, ctx):
    q = update.callback_query
    await q.answer()  # IMPORTANTE: siempre answer() para quitar el spinner
    if q.data == "opt_a":
        await q.edit_message_text("Elegiste A")

app.add_handler(CommandHandler("menu", menu))
app.add_handler(CallbackQueryHandler(boton))
```

## JobQueue (APScheduler integrado)

Requiere el extra `[job-queue]` (ya en requirements.txt).

### Job diario

```python
from datetime import time

async def recordatorio(context):
    bot = context.bot
    await bot.send_message(chat_id=USER_ID, text="Recuerda registrar tu entreno hoy.")

app.job_queue.run_daily(
    recordatorio,
    time=time(hour=8, minute=0),
    name="recordatorio_diario",
)
```

### Job semanal (solo lunes)

```python
app.job_queue.run_daily(
    recordatorio_peso,
    time=time(hour=8, minute=0),
    days=(0,),  # 0=Lunes, 1=Martes, ..., 6=Domingo
    name="recordatorio_peso",
)
```

EntrenadorAX define 6 jobs en [src/telegram/scheduler.py](../../../src/telegram/scheduler.py).

### Job one-shot

```python
app.job_queue.run_once(callback, when=300, name="follow_up_5min")  # 5 min despues
```

### Job repeating (cada N segundos)

```python
app.job_queue.run_repeating(callback, interval=3600, first=10, name="cleanup")
```

### Verificar JobQueue disponible

```python
if app.job_queue is None:
    logger.warning("JobQueue no disponible. Instala python-telegram-bot[job-queue]")
    return
```

EntrenadorAX ya lo verifica en `registrar_jobs()`.

## Error handler global

```python
import traceback
import html

async def error_handler(update, context):
    logger.error("Exception en handler", exc_info=context.error)

    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    message = (
        f"Excepcion en el bot:\n"
        f"<pre>update = {html.escape(str(update))[:1000]}</pre>\n"
        f"<pre>{html.escape(tb_string)[:2500]}</pre>"
    )

    # Notificar al developer
    await context.bot.send_message(
        chat_id=DEVELOPER_CHAT_ID,
        text=message,
        parse_mode="HTML",
    )

app.add_error_handler(error_handler)
```

EntrenadorAX deberia agregar esto (hoy solo loggea, no notifica al dev).

## Webhook setup (Telegram side)

Configurar el webhook desde tu terminal una sola vez (NO desde el codigo del bot):

```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -d "url=https://entrenador.railway.app/webhook" \
  -d "secret_token=<SECRET_DE_TU_BOT>"
```

EntrenadorAX expone `/webhook-info` que devuelve el secret a usar.

Verificar:

```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

## Filtros utiles

| Filtro | Que captura |
|---|---|
| `filters.TEXT` | Cualquier texto |
| `filters.COMMAND` | Mensajes que empiezan con `/` |
| `filters.PHOTO` | Fotos |
| `filters.VOICE` | Voice notes |
| `filters.AUDIO` | Audio files |
| `filters.VIDEO` | Videos |
| `filters.Document.PDF` | PDFs |
| `filters.LOCATION` | Ubicaciones |
| `filters.CONTACT` | Contactos |
| `filters.Regex(r"^pattern")` | Texto que matchea regex |
| `filters.User(user_id=123)` | Solo un usuario especifico |
| `filters.ChatType.PRIVATE` | Solo chats privados (no grupos) |

Combinables con `&` (AND), `|` (OR), `~` (NOT):

```python
# Solo texto en chat privado, sin comandos
MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handler)
```

## Send actions (UX)

Avisar al usuario que el bot esta "ocupado":

```python
await update.message.chat.send_action("typing")     # mas comun
await update.message.chat.send_action("upload_photo")
await update.message.chat.send_action("upload_voice")
await update.message.chat.send_action("record_voice")
```

Dura ~5 segundos. Si la operacion dura mas, repetir periodicamente (o usar contextmanager).

## Rate limiting de Telegram

| Limite | Valor |
|---|---|
| Mensajes a un MISMO chat | 1/segundo (burst hasta 30) |
| Mensajes globales del bot | 30/segundo |
| sendMessage en grupos | 20/minuto por grupo |

Si los superas, recibes `RetryAfter`. La solucion es respetar `retry_after`. EntrenadorAX ya implementa rate limit propio en `middlewares.py` (10 msg/min por usuario, Redis sorted set).

## Migration / breaking changes en v22

- v20 -> v22: API es completamente async. Si encuentras codigo `app.run_polling()` sincronico, es API legacy.
- `ContextTypes` se simplifico; usar `ContextTypes.DEFAULT_TYPE` raramente necesario.
- `JobQueue` ahora es opcional como extra `[job-queue]`.
- `Application.builder()` reemplaza `Updater(...)`.

## Testing handlers

```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_start_handler():
    update = AsyncMock()
    update.effective_user.id = 123
    update.effective_user.first_name = "Test"
    update.message.reply_text = AsyncMock()
    ctx = AsyncMock()

    await start(update, ctx)

    update.message.reply_text.assert_called_once()
```

## Logging recomendado

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# Silenciar verbose libs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
```
