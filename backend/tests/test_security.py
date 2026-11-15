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
