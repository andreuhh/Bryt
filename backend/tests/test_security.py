import pytest
from cryptography.fernet import Fernet

from app.core import security
from app.core.config import Settings


def test_encrypt_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(encryption_key=Fernet.generate_key().decode())
    monkeypatch.setattr(security, "get_settings", lambda: settings)

    token = security.encrypt_secret("intervals-key-123")
    assert token != "intervals-key-123"
    assert security.decrypt_secret(token) == "intervals-key-123"


def test_missing_key_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "get_settings", lambda: Settings(encryption_key=""))
    with pytest.raises(RuntimeError):
        security.encrypt_secret("x")


@pytest.mark.parametrize(
    ("key", "message"), [("", "missing"), ("not-a-fernet-key", "not a valid Fernet key")]
)
def test_startup_check_rejects_missing_or_invalid_key(
    monkeypatch: pytest.MonkeyPatch, key: str, message: str
) -> None:
    monkeypatch.setattr(security, "get_settings", lambda: Settings(encryption_key=key))
    with pytest.raises(RuntimeError, match=message):
        security.check_encryption_key()


def test_startup_check_accepts_valid_key(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(encryption_key=Fernet.generate_key().decode())
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    security.check_encryption_key()
