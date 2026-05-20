"""Script para emitir un comunicado optimista de restablecimiento de servicio a todos los usuarios activos.

Se ejecuta cuando la base de datos y los servicios de Railway vuelven a estar operativos.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import os
from telegram import Bot
from telegram.error import Forbidden, BadRequest, RetryAfter

# Asegurar que el script puede importar desde src
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import settings
from src.db.connection import init_db, close_db
from src.db.repository import listar_usuarios_activos

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("broadcast_outage")

# Mensaje optimista de restablecimiento de servicio
COMUNICADO = """<b>⚡ ¡Buenas noticias: EntrenadorAX está de regreso! ⚡</b>

Hola deportista, espero que estés con toda la energía.

Nuestro proveedor de infraestructura en la nube (Railway) ha solucionado la interrupción técnica mayor y todos los servicios de EntrenadorAX se están restableciendo exitosamente.

<b>¿Qué significa esto para ti?</b>
1. <b>Servicio Activo:</b> Ya puedes escribirme de nuevo para registrar tus entrenamientos, comidas, peso, sueño e hidratación con total normalidad.
2. <b>Estabilidad Gradual:</b> Como los servidores se están reactivando progresivamente a nivel global, es posible que experimentes algún leve retraso puntual en las respuestas durante las próximas horas. ¡Pero ya todo está operativo!
3. <b>Datos 100% Seguros:</b> Tu perfil, planes de entrenamiento y racha (streak) están completamente intactos y a salvo.

Lamentamos el inconveniente temporal ajeno a nosotros. ¡Gracias infinitas por tu paciencia, apoyo y disciplina habitual! 💪🤖

¡Vamos con toda a retomar el entrenamiento hoy!
"""

async def main():
    logger.info("Iniciando transmisión de comunicado optimista...")
    
    # 1. Inicializar DB
    await init_db()
    
    try:
        # 2. Obtener usuarios activos usando el repositorio existente
        usuarios = await listar_usuarios_activos()
        total_usuarios = len(usuarios)
        logger.info(f"Se encontraron {total_usuarios} usuarios activos elegibles en la base de datos.")
        
        if total_usuarios == 0:
            logger.warning("No hay usuarios activos registrados para enviar el mensaje.")
            return
            
        # 3. Inicializar Bot de Telegram directamente
        bot_token = settings.telegram_token.get_secret_value()
        bot = Bot(token=bot_token)
        
        # 4. Enviar mensajes con control de tasa (rate limiting)
        exitosos = 0
        bloqueados = 0
        fallidos = 0
        
        for i, usuario in enumerate(usuarios, 1):
            chat_id = usuario.telegram_id
            nombre_usuario = usuario.nombre or "deportista"
            logger.info(f"[{i}/{total_usuarios}] Enviando a {nombre_usuario} (ID: {chat_id})...")
            
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=COMUNICADO,
                    parse_mode="HTML"
                )
                exitosos += 1
                # Telegram limita a un máximo de 30 mensajes por segundo para difusiones globales.
                # Añadimos un pequeño delay de 0.05 segundos para estar seguros y evitar límites de tasa.
                await asyncio.sleep(0.05)
                
            except Forbidden:
                # El usuario bloqueó al bot
                logger.warning(f"El usuario {chat_id} bloqueó al bot.")
                bloqueados += 1
                
            except RetryAfter as e:
                # Nos pasamos del rate-limit, Telegram nos pide esperar e.retry_after segundos
                logger.warning(f"Rate limit alcanzado. Esperando {e.retry_after} segundos...")
                await asyncio.sleep(e.retry_after)
                # Reintentar el envío una vez más
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=COMUNICADO,
                        parse_mode="HTML"
                    )
                    exitosos += 1
                except Exception as ex:
                    logger.error(f"Error en reintento para {chat_id}: {ex}")
                    fallidos += 1
                    
            except BadRequest as e:
                logger.error(f"Error de solicitud para {chat_id}: {e}")
                fallidos += 1
                
            except Exception as e:
                logger.error(f"Error inesperado al enviar a {chat_id}: {e}")
                fallidos += 1
                
        logger.info("=== RESUMEN DE TRANSMISIÓN ===")
        logger.info(f"Total procesados: {total_usuarios}")
        logger.info(f"Enviados con éxito: {exitosos}")
        logger.info(f"Bloqueados (Forbidden): {bloqueados}")
        logger.info(f"Fallidos: {fallidos}")
        
    finally:
        await close_db()

if __name__ == "__main__":
    asyncio.run(main())
