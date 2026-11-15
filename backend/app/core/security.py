"""Symmetric encryption for third-party credentials stored per tenant."""

from cryptography.fernet import Fernet

from app.core.config import get_settings


def _fernet() -> Fernet:
    key = get_settings().encryption_key
    if not key:
        raise RuntimeError("ENCRYPTION_KEY is not configured")
    return Fernet(key.encode())


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
