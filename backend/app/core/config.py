"""Application settings loaded from environment / .env."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "BRYT"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # PostgreSQL (Supabase-compatible). Async driver required.
    database_url: str = "postgresql+asyncpg://bryt:bryt@localhost:5432/bryt"

    # Fernet key used to encrypt per-user secrets (e.g. Intervals.icu API keys) at rest.
    encryption_key: str = ""

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"

    # Intervals.icu
    intervals_base_url: str = "https://intervals.icu/api/v1"
    intervals_webhook_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
