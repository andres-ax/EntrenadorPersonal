"""CRUD conversaciones multicanal + Redis hilo activo."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select, update

from src.cache import get_redis
from src.db.connection import async_session_factory
from src.db.models import (
    CanalConversacion,
    Conversacion,
    MensajeChat,
    RolMensajeChat,
    Usuario,
)

logger = logging.getLogger(__name__)

CONV_ACTIVA_TTL = 60 * 60 * 24 * 90  # 90 dias


def session_key_for_conversacion(conversacion_id: int) -> str:
    return f"conv:{conversacion_id}"


def _conv_activa_key(telegram_id: int) -> str:
    return f"user:{telegram_id}:conv_activa"


async def _get_usuario_id_by_telegram(telegram_id: int) -> int | None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario.id).where(Usuario.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


async def asegurar_conversacion_principal(telegram_id: int) -> Conversacion:
    """Crea hilo principal si no existe (migracion lazy por usuario)."""
    user_id = await _get_usuario_id_by_telegram(telegram_id)
    if user_id is None:
        from src.db.repository import obtener_o_crear_usuario

        user = await obtener_o_crear_usuario(telegram_id)
        user_id = user.id

    async with async_session_factory() as session:
        result = await session.execute(
            select(Conversacion).where(
                Conversacion.usuario_id == user_id,
                Conversacion.es_principal == True,  # noqa: E712
            )
        )
        conv = result.scalar_one_or_none()
        if conv is not None:
            return conv

        conv = Conversacion(
            usuario_id=user_id,
            titulo="Coach",
            canal_creador=CanalConversacion.TELEGRAM,
            es_principal=True,
            activa=True,
            ultimo_mensaje_en=datetime.utcnow(),
        )
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
        await fijar_conversacion_activa(telegram_id, conv.id)
        return conv


async def crear_conversacion(
    user_id: int,
    titulo: str = "Nuevo hilo",
    canal: CanalConversacion = CanalConversacion.ANDROID,
) -> Conversacion:
    async with async_session_factory() as session:
        conv = Conversacion(
            usuario_id=user_id,
            titulo=titulo[:120],
            canal_creador=canal,
            activa=True,
            ultimo_mensaje_en=datetime.utcnow(),
        )
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
        return conv


async def listar_conversaciones(
    user_id: int,
    limit: int = 30,
    offset: int = 0,
    incluir_inactivas: bool = False,
) -> list[Conversacion]:
    async with async_session_factory() as session:
        query = select(Conversacion).where(Conversacion.usuario_id == user_id)
        if not incluir_inactivas:
            query = query.where(Conversacion.activa == True)  # noqa: E712
        query = query.order_by(Conversacion.ultimo_mensaje_en.desc().nullslast())
        query = query.limit(limit).offset(offset)
        result = await session.execute(query)
        return list(result.scalars().all())


async def obtener_conversacion(conv_id: int, user_id: int) -> Conversacion | None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Conversacion).where(
                Conversacion.id == conv_id,
                Conversacion.usuario_id == user_id,
            )
        )
        return result.scalar_one_or_none()


async def fijar_conversacion_activa(telegram_id: int, conv_id: int) -> None:
    client = await get_redis()
    await client.setex(_conv_activa_key(telegram_id), CONV_ACTIVA_TTL, str(conv_id))


async def obtener_conversacion_activa(telegram_id: int) -> Conversacion:
    client = await get_redis()
    raw = await client.get(_conv_activa_key(telegram_id))
    if raw:
        try:
            conv_id = int(raw)
            user_id = await _get_usuario_id_by_telegram(telegram_id)
            if user_id:
                conv = await obtener_conversacion(conv_id, user_id)
                if conv and conv.activa:
                    return conv
        except (TypeError, ValueError):
            pass
    return await asegurar_conversacion_principal(telegram_id)


async def archivar_conversacion(conv_id: int, user_id: int) -> bool:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Conversacion).where(
                Conversacion.id == conv_id,
                Conversacion.usuario_id == user_id,
                Conversacion.es_principal == False,  # noqa: E712
            )
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            return False
        conv.activa = False
        await session.commit()
        return True


async def renombrar_conversacion(conv_id: int, user_id: int, titulo: str) -> bool:
    async with async_session_factory() as session:
        result = await session.execute(
            update(Conversacion)
            .where(Conversacion.id == conv_id, Conversacion.usuario_id == user_id)
            .values(titulo=titulo[:120])
        )
        await session.commit()
        return result.rowcount > 0


async def guardar_mensaje(
    conversacion_id: int,
    rol: RolMensajeChat,
    contenido: str,
    canal: CanalConversacion,
    *,
    es_desde_telegram: bool = False,
    metadata: dict[str, Any] | None = None,
) -> MensajeChat:
    ahora = datetime.utcnow()
    async with async_session_factory() as session:
        msg = MensajeChat(
            conversacion_id=conversacion_id,
            rol=rol,
            contenido=contenido,
            canal_origen=canal,
            es_desde_telegram=es_desde_telegram,
            metadata_json=metadata,
            creado_en=ahora,
        )
        session.add(msg)
        await session.execute(
            update(Conversacion)
            .where(Conversacion.id == conversacion_id)
            .values(ultimo_mensaje_en=ahora)
        )
        await session.commit()
        await session.refresh(msg)
        return msg


async def listar_mensajes(
    conversacion_id: int,
    *,
    before_id: int | None = None,
    limit: int = 50,
) -> list[MensajeChat]:
    async with async_session_factory() as session:
        query = select(MensajeChat).where(MensajeChat.conversacion_id == conversacion_id)
        if before_id is not None:
            query = query.where(MensajeChat.id < before_id)
        query = query.order_by(MensajeChat.id.desc()).limit(limit)
        result = await session.execute(query)
        items = list(result.scalars().all())
        items.reverse()
        return items


async def titulo_auto_desde_mensaje(texto: str) -> str:
    t = texto.strip().replace("\n", " ")[:60]
    return t or "Nuevo hilo"
