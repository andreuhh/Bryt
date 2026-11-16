"""Executed activities (from Intervals.icu or manual .fit upload) and their time series."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, UniqueConstraint
from sqlmodel import Field

from app.models.base import IdMixin, TenantMixin, TimestampMixin, enum_column, jsonb_column
from app.models.enums import ActivitySource, Surface, SurfaceSource


class Activity(IdMixin, TimestampMixin, TenantMixin, table=True):
    __tablename__ = "activities"
    __table_args__ = (
        # Idempotent sync: same external activity never ingested twice per user
        UniqueConstraint("user_id", "source", "external_id", name="uq_activity_external"),
        # Idempotent upload: same .fit file never ingested twice per user
        UniqueConstraint("user_id", "fit_sha256", name="uq_activity_fit_hash"),
        Index("ix_activity_user_start", "user_id", "start_time"),
    )

    source: ActivitySource = Field(sa_column=enum_column(ActivitySource))
    external_id: str | None = Field(default=None, max_length=64)
    fit_sha256: str | None = Field(default=None, max_length=64)
    fit_storage_path: str | None = Field(default=None, max_length=512)

    name: str | None = Field(default=None, max_length=200)
    sport: str = Field(default="running", max_length=32)
    start_time: datetime = Field(sa_type=DateTime(timezone=True))

    # Summary metrics (deterministic, from the .fit parser)
    duration_s: int = Field(ge=0)
    moving_time_s: int | None = Field(default=None, ge=0)
    distance_m: float = Field(ge=0)
    avg_pace_s_per_km: float | None = Field(default=None, gt=0)
    avg_hr: float | None = Field(default=None, gt=0)
    max_hr: float | None = Field(default=None, gt=0)
    avg_cadence_spm: float | None = Field(default=None, gt=0)
    avg_ground_contact_ms: float | None = Field(default=None, gt=0)
    elevation_gain_m: float | None = Field(default=None, ge=0)
    elevation_loss_m: float | None = Field(default=None, ge=0)
    # Derived by services (STEP 3): cadence-vs-HR divergence, drift, etc.
    computed_metrics: dict[str, Any] = Field(default_factory=dict, sa_column=jsonb_column())

    # Contextual tags (ContextTags in app.schemas.activity)
    surface: Surface | None = Field(default=None, sa_column=enum_column(Surface, nullable=True))
    surface_source: SurfaceSource | None = Field(
        default=None, sa_column=enum_column(SurfaceSource, nullable=True)
    )
    context_tags: dict[str, Any] = Field(default_factory=dict, sa_column=jsonb_column())


class ActivityStream(IdMixin, TimestampMixin, TenantMixin, table=True):
    """Time series kept apart from Activity so calendar/list queries stay light.

    All arrays share the same length and are aligned on `elapsed_s`.
    """

    __tablename__ = "activity_streams"

    activity_id: uuid.UUID = Field(foreign_key="activities.id", unique=True, ondelete="CASCADE")
    sample_count: int = Field(ge=0)
    elapsed_s: list[float] = Field(default_factory=list, sa_column=jsonb_column())
    distance_m: list[float | None] = Field(default_factory=list, sa_column=jsonb_column())
    pace_s_per_km: list[float | None] = Field(default_factory=list, sa_column=jsonb_column())
    heart_rate: list[float | None] = Field(default_factory=list, sa_column=jsonb_column())
    cadence_spm: list[float | None] = Field(default_factory=list, sa_column=jsonb_column())
    elevation_m: list[float | None] = Field(default_factory=list, sa_column=jsonb_column())
    ground_contact_ms: list[float | None] = Field(default_factory=list, sa_column=jsonb_column())
