from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

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


async def obtener_usuario_por_id(user_id: int) -> Usuario | None:
    async with async_session_factory() as session:
        result = await session.execute(select(Usuario).where(Usuario.id == user_id))
        return result.scalar_one_or_none()


def _ajustar_auth_method_tras_desvincular(usuario: Usuario) -> None:
    """Solo baja auth_method cuando el usuario tenía ambos métodos."""
    if usuario.auth_method == "both":
        usuario.auth_method = "phone_email"


def _ajustar_auth_method_tras_vincular(usuario: Usuario) -> None:
    if usuario.telefono and usuario.email and usuario.phone_verified_at:
        usuario.auth_method = "both"
    elif usuario.auth_method == "phone_email":
        usuario.auth_method = "both"


async def link_telegram_to_user(user_id: int, telegram_id: int) -> Usuario:
    """Asocia de manera segura un telegram_id a un usuario existente.

    Si el telegram_id ya pertenecía a otro usuario, primero lo libera en un
    commit separado (PostgreSQL exige esto por la UNIQUE en telegram_id).
    """
    async with async_session_factory() as session:
        existing_owner_q = await session.execute(
            select(Usuario).where(
                Usuario.telegram_id == telegram_id,
                Usuario.id != user_id,
            )
        )
        existing_owner = existing_owner_q.scalar_one_or_none()

        if existing_owner is not None:
            logger.warning(
                "Desvinculando telegram_id=%s de usuario_id=%s por re-asociación a usuario_id=%s",
                telegram_id,
                existing_owner.id,
                user_id,
            )
            existing_owner.telegram_id = None
            _ajustar_auth_method_tras_desvincular(existing_owner)
            session.add(existing_owner)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                logger.exception(
                    "Fallo al desvincular telegram_id=%s de usuario_id=%s",
                    telegram_id,
                    existing_owner.id,
                )
                raise

    async with async_session_factory() as session:
        user_q = await session.execute(select(Usuario).where(Usuario.id == user_id))
        user = user_q.scalar_one_or_none()
        if user is None:
            raise ValueError(f"Usuario con ID {user_id} no encontrado")

        user.telegram_id = telegram_id
        _ajustar_auth_method_tras_vincular(user)
        session.add(user)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.exception(
                "Fallo al vincular telegram_id=%s a usuario_id=%s",
                telegram_id,
                user_id,
            )
            raise
        await session.refresh(user)
        return user
