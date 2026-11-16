"""Athlete identity, lifestyle profile and personal bests."""

import uuid
from datetime import date

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import IdMixin, TenantMixin, TimestampMixin, enum_column, jsonb_column
from app.models.enums import (
    AthleteBackground,
    HrSensor,
    Methodology,
    StrengthSetting,
    Surface,
    TrainingSlot,
    Weekday,
    WorkType,
)


class User(TimestampMixin, table=True):
    """Public profile row. `id` IS the Supabase Auth user id (auth.users.id): never generated."""

    __tablename__ = "users"

    id: uuid.UUID = Field(primary_key=True)
    email: str = Field(max_length=320, unique=True, index=True)
    display_name: str | None = Field(default=None, max_length=120)
    timezone: str = Field(default="Europe/Rome", max_length=64)
    onboarding_completed: bool = Field(default=False)


class UserLifestyleProfile(IdMixin, TimestampMixin, TenantMixin, table=True):
    """Everything the TrainingPeriodizationAgent needs before generating a plan."""

    __tablename__ = "user_lifestyle_profiles"

    # One profile per user (overrides TenantMixin: unique instead of plain index)
    user_id: uuid.UUID = Field(foreign_key="users.id", unique=True, ondelete="CASCADE")

    # Athlete background & physiology (all zones are derived from these, never hardcoded)
    background: AthleteBackground = Field(sa_column=enum_column(AthleteBackground))
    birth_year: int | None = Field(default=None, ge=1920, le=2020)
    weight_kg: float | None = Field(default=None, gt=0)
    threshold_hr: int | None = Field(default=None, gt=0, le=230)
    max_hr: int | None = Field(default=None, gt=0, le=240)
    resting_hr: int | None = Field(default=None, gt=0, le=120)
    weekly_volume_km: float | None = Field(default=None, ge=0)  # usual, last 8-12 weeks
    peak_volume_km: float | None = Field(default=None, ge=0)  # highest week in a past build-up

    # Target race
    target_race_name: str | None = Field(default=None, max_length=160)
    target_race_date: date | None = None
    target_race_distance_m: int | None = Field(default=None, gt=0)
    target_race_time_s: int | None = Field(default=None, gt=0)
    target_race_surface: Surface | None = Field(
        default=None, sa_column=enum_column(Surface, nullable=True)
    )
    target_race_elevation_gain_m: int | None = Field(default=None, ge=0)

    # Lifestyle & habits
    preferred_slot: TrainingSlot = Field(sa_column=enum_column(TrainingSlot))
    available_days: list[Weekday] = Field(default_factory=list, sa_column=jsonb_column())
    work_type: WorkType = Field(sa_column=enum_column(WorkType))
    avg_sleep_hours: float | None = Field(default=None, ge=0, le=14)
    terrain_access: list[Surface] = Field(default_factory=list, sa_column=jsonb_column())
    methodology: Methodology = Field(
        default=Methodology.TRADITIONAL, sa_column=enum_column(Methodology)
    )
    double_sessions_ok: bool = Field(default=False, sa_column_kwargs={"server_default": "false"})
    long_run_day: Weekday | None = Field(
        default=None, sa_column=enum_column(Weekday, nullable=True)
    )
    strength_sessions_per_week: int = Field(
        default=0, ge=0, le=7, sa_column_kwargs={"server_default": "0"}
    )
    strength_setting: StrengthSetting = Field(
        default=StrengthSetting.NONE,
        sa_column=enum_column(StrengthSetting, server_default=StrengthSetting.NONE),
    )
    hr_sensor: HrSensor | None = Field(default=None, sa_column=enum_column(HrSensor, nullable=True))
    injury_notes: str | None = Field(default=None, max_length=1000)
    # Free text for the agents (e.g. how the last race went, fueling, constraints)
    coach_notes: str | None = Field(default=None, max_length=2000)

    # Intervals.icu integration — API key is ONLY stored Fernet-encrypted
    intervals_athlete_id: str | None = Field(default=None, max_length=32)
    intervals_api_key_encrypted: str | None = Field(default=None, repr=False)

    @property
    def intervals_connected(self) -> bool:
        return bool(self.intervals_athlete_id and self.intervals_api_key_encrypted)


class PersonalBest(IdMixin, TimestampMixin, TenantMixin, table=True):
    """One row per PB: keeps history so calibration can weight recent results."""

    __tablename__ = "personal_bests"
    __table_args__ = (Index("ix_pb_user_distance_date", "user_id", "distance_m", "achieved_on"),)

    distance_m: int = Field(gt=0)
    time_s: int = Field(gt=0)
    achieved_on: date
    surface: Surface = Field(default=Surface.ASPHALT, sa_column=enum_column(Surface))
    elevation_gain_m: int | None = Field(default=None, ge=0)
    event_name: str | None = Field(default=None, max_length=160)
