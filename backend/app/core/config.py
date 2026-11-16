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

    # Supabase Auth. JWKS (asymmetric keys) is used when supabase_url is set;
    # supabase_jwt_secret only for legacy HS256 projects.
    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    supabase_jwt_audience: str = "authenticated"

    # Anthropic / agents
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"  # every agent without an override below
    # Per-agent model overrides (empty = anthropic_model), chosen on a side-by-side run over
    # real inputs: Haiku matched Opus on the nutrition numbers, Sonnet was close on chat;
    # the mechanical analysis and the plan stay on Opus.
    mechanical_load_model: str = ""
    training_periodization_model: str = ""
    nutrition_recovery_model: str = "claude-haiku-5-5"
    coach_chat_model: str = "claude-sonnet-5-5"
    agents_enabled: bool = True  # run the post-activity pipeline automatically after ingestion
    # Weekly refinement scheduler (Sunday evening, athlete's local time)
    scheduler_enabled: bool = True
    scheduler_interval_s: int = 1800
    # Paid agent analyses per activity requested by the athlete: the first one + re-analyses
    # after editing the tags (raise when users ask for it)
    max_analyses_per_activity: int = 2
    # Coach chat: messages per athlete per local day (cost guardrail, checked before the LLM)
    chat_daily_limit: int = 15

    # Intervals.icu
    intervals_base_url: str = "https://intervals.icu/api/v1"
    intervals_webhook_secret: str = ""
    intervals_sync_default_days: int = 14
    intervals_timeout_s: float = 30.0
    # Periodic poll (personal API keys get no webhooks): new runs within one interval
    intervals_poll_enabled: bool = True
    intervals_poll_interval_s: int = 900

    # Ingestion
    storage_dir: str = "storage"
    max_fit_upload_mb: int = 25

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    def model_for(self, agent: str) -> str:
        """Model of an agent (AgentName value): its override, else anthropic_model."""
        override: str = getattr(self, f"{agent.lower()}_model")
        return override or self.anthropic_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
