"""Cifrado simetrico Fernet para tokens OAuth de wearables.

FERNET_KEY debe ser un string base64 url-safe de 32 bytes:
    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from src.config import settings

logger = logging.getLogger(__name__)

_cipher: Optional[Fernet] = None


def _get_cipher() -> Optional[Fernet]:
    global _cipher
    if _cipher is not None:
        return _cipher
    if settings.fernet_key is None:
        logger.warning("FERNET_KEY no seteada. Tokens wearables guardados en claro.")
        return None
    key = settings.fernet_key.get_secret_value()
    try:
        _cipher = Fernet(key.encode())
    except Exception:
        logger.exception("FERNET_KEY invalida")
        return None
    return _cipher


def encrypt_str(plaintext: str) -> str:
    """Cifra string a base64. Si no hay key, devuelve el plaintext con prefijo."""
    cipher = _get_cipher()
    if cipher is None:
        return f"plain::{plaintext}"
    return cipher.encrypt(plaintext.encode()).decode()


def decrypt_str(ciphertext: str) -> Optional[str]:
    """Descifra. Si el valor tiene prefijo plain::, devuelve sin cifrar."""
    if ciphertext.startswith("plain::"):
        return ciphertext[7:]
    cipher = _get_cipher()
    if cipher is None:
        return None
    try:
        return cipher.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.warning("Token inválido al descifrar (rotacion de FERNET_KEY?)")
        return None
