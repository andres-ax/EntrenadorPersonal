from __future__ import annotations

import logging
from sqlalchemy import select
from src.db.connection import async_session_factory
from src.db.models import Usuario

logger = logging.getLogger(__name__)

def normalize_phone(phone: str) -> str:
    """Normaliza un número al formato E.164 colombiano (+57 + 10 dígitos móvil).

    Acepta entradas con o sin '+', con o sin código de país duplicado
    (ej. 573044093197 o +57573044093197 → +573044093197).
    """
    digits = "".join(c for c in phone if c.isdigit())
    if not digits:
        return phone.strip()

    # Quitar 57 repetido: +57573044093197 → 573044093197
    while len(digits) > 12 and digits.startswith("57"):
        digits = digits[2:]

    if digits.startswith("57") and len(digits) == 12:
        return f"+{digits}"

    if len(digits) == 10 and digits[0] == "3":
        return f"+57{digits}"

    if not digits.startswith("57"):
        return f"+57{digits}"

    return f"+{digits}"

async def resolve_user_by_phone(phone: str) -> Usuario | None:
    """Busca un usuario por su número de teléfono.

    Args:
        phone: número de teléfono (ej: +573001234567)
    """
    normalized = normalize_phone(phone)
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telefono == normalized)
        )
        return result.scalar_one_or_none()

async def resolve_user_by_telegram(telegram_id: int) -> Usuario | None:
    """Busca un usuario por su telegram_id.

    Args:
        telegram_id: ID de Telegram
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

async def link_telegram_to_user(user_id: int, telegram_id: int) -> Usuario:
    """Asocia de manera segura un telegram_id a un usuario existente.

    Para evitar violaciones de clave única, si el telegram_id ya estaba
    asociado a otro usuario, se desvincula de ese usuario antiguo antes
    de asociarlo al nuevo.

    Args:
        user_id: ID interno del usuario
        telegram_id: ID de Telegram a vincular
    """
    async with async_session_factory() as session:
        # 1. Verificar conflicto de clave única
        existing_owner_q = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        existing_owner = existing_owner_q.scalar_one_or_none()

        if existing_owner and existing_owner.id != user_id:
            logger.warning(
                "Desvinculando telegram_id=%s de usuario_id=%s por re-asociación a usuario_id=%s",
                telegram_id,
                existing_owner.id,
                user_id,
            )
            existing_owner.telegram_id = None
            if existing_owner.auth_method == "both":
                existing_owner.auth_method = "phone_email"
            elif existing_owner.auth_method == "telegram":
                existing_owner.auth_method = "phone_email"
            session.add(existing_owner)

        # 2. Vincular al nuevo usuario
        user_q = await session.execute(
            select(Usuario).where(Usuario.id == user_id)
        )
        user = user_q.scalar_one_or_none()
        if user is None:
            raise ValueError(f"Usuario con ID {user_id} no encontrado")

        user.telegram_id = telegram_id
        if user.auth_method == "phone_email":
            user.auth_method = "both"

        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user
