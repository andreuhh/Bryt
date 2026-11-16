"""Symmetric encryption for third-party credentials stored per tenant."""

from cryptography.fernet import Fernet

from app.core.config import get_settings

GENERATE_HINT = (
    'generate one with: .venv/bin/python -c "from cryptography.fernet import Fernet; '
    'print(Fernet.generate_key().decode())"'
)


def check_encryption_key() -> None:
    """Startup check: fail fast with a clear message instead of a 500 on the first save of an
    Intervals.icu key (which the browser shows as a CORS / "backend unreachable" error)."""
    key = get_settings().encryption_key
    if not key:
        raise RuntimeError(f"ENCRYPTION_KEY is missing in backend/.env: {GENERATE_HINT}")
    try:
        Fernet(key.encode())
    except ValueError as exc:
        raise RuntimeError(f"ENCRYPTION_KEY is not a valid Fernet key: {GENERATE_HINT}") from exc


def _fernet() -> Fernet:
    key = get_settings().encryption_key
    if not key:
        raise RuntimeError("ENCRYPTION_KEY is not configured")
    return Fernet(key.encode())


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
