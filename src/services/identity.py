from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

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
    """Busca un usuario por su número de teléfono."""
    normalized = normalize_phone(phone)
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telefono == normalized)
        )
        return result.scalar_one_or_none()


async def resolve_user_by_telegram(telegram_id: int) -> Usuario | None:
    """Busca un usuario por su telegram_id."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


async def obtener_usuario_por_id(user_id: int) -> Usuario | None:
    async with async_session_factory() as session:
        result = await session.execute(select(Usuario).where(Usuario.id == user_id))
        return result.scalar_one_or_none()


def _temp_telegram_id(user_id: int) -> int:
    """ID temporal único para liberar telegram_id real sin dejar NULL expuesto."""
    return -user_id


def _ajustar_auth_method_tras_desvincular(usuario: Usuario) -> None:
    if usuario.auth_method == "both":
        usuario.auth_method = "phone_email"


def _ajustar_auth_method_tras_vincular(usuario: Usuario) -> None:
    if usuario.telefono and usuario.email and usuario.phone_verified_at:
        usuario.auth_method = "both"
    elif usuario.auth_method == "phone_email":
        usuario.auth_method = "both"


async def _limpiar_telegram_id_temporal(former_user_id: int) -> None:
    """Best-effort: deja NULL el placeholder -user_id tras mover el Telegram real."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.id == former_user_id)
        )
        former = result.scalar_one_or_none()
        if former is None or former.telegram_id != _temp_telegram_id(former_user_id):
            return
        former.telegram_id = None
        session.add(former)
        try:
            await session.commit()
        except SQLAlchemyError:
            logger.warning(
                "No se pudo limpiar telegram_id temporal de usuario_id=%s",
                former_user_id,
                exc_info=True,
            )


async def link_telegram_to_user(user_id: int, telegram_id: int) -> Usuario:
    """Asocia telegram_id al usuario de la app de forma atómica.

    Si el ID ya pertenecía a otro usuario, primero lo mueve a un placeholder
    negativo (-user_id) en la misma transacción. Así PostgreSQL no viola UNIQUE
    y ningún handler concurrente puede «robar» el ID en un hueco NULL.
    """
    former_user_id: int | None = None

    async with async_session_factory() as session:
        existing_owner_q = await session.execute(
            select(Usuario).where(
                Usuario.telegram_id == telegram_id,
                Usuario.id != user_id,
            )
        )
        existing_owner = existing_owner_q.scalar_one_or_none()

        user_q = await session.execute(select(Usuario).where(Usuario.id == user_id))
        user = user_q.scalar_one_or_none()
        if user is None:
            raise ValueError(f"Usuario con ID {user_id} no encontrado")

        if existing_owner is not None:
            former_user_id = existing_owner.id
            logger.warning(
                "Desvinculando telegram_id=%s de usuario_id=%s por re-asociación a usuario_id=%s",
                telegram_id,
                existing_owner.id,
                user_id,
            )
            existing_owner.telegram_id = _temp_telegram_id(existing_owner.id)
            _ajustar_auth_method_tras_desvincular(existing_owner)
            session.add(existing_owner)
            await session.flush()

        if user.telegram_id == telegram_id:
            return user

        user.telegram_id = telegram_id
        _ajustar_auth_method_tras_vincular(user)
        session.add(user)
        try:
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
            logger.exception(
                "Fallo al vincular telegram_id=%s a usuario_id=%s",
                telegram_id,
                user_id,
            )
            raise
        await session.refresh(user)

    if former_user_id is not None:
        await _limpiar_telegram_id_temporal(former_user_id)

    return user
