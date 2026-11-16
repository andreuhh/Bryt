"""User, lifestyle profile, personal bests and onboarding payload."""

import uuid
from datetime import date, datetime
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator

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
from app.schemas.common import ORMModel, StrictModel

# What a generic watch "Run" usually means for this athlete (trail/track/treadmill have their
# own watch modes, recorded in the .fit)
RunSurfaceDefault = Literal[Surface.ASPHALT, Surface.GRAVEL, Surface.MIXED]

INTERVALS_ATHLETE_ID_PATTERN = r"^i\d+$"


class UserRead(ORMModel):
    id: uuid.UUID
    email: str  # read model: stored value, not re-validated
    display_name: str | None
    timezone: str
    onboarding_completed: bool


class PersonalBestCreate(StrictModel):
    distance_m: int = Field(gt=0)
    time_s: int = Field(gt=0)
    achieved_on: date
    surface: Surface = Surface.ASPHALT
    elevation_gain_m: int | None = Field(default=None, ge=0)
    event_name: str | None = Field(default=None, max_length=160)


class PersonalBestRead(ORMModel):
    id: uuid.UUID
    distance_m: int
    time_s: int
    achieved_on: date
    surface: Surface
    elevation_gain_m: int | None
    event_name: str | None


class _ProfileFields(StrictModel):
    background: AthleteBackground
    birth_year: int | None = Field(default=None, ge=1920, le=2020)
    weight_kg: float | None = Field(default=None, gt=0)
    threshold_hr: int | None = Field(default=None, gt=0, le=230)
    max_hr: int | None = Field(default=None, gt=0, le=240)
    resting_hr: int | None = Field(default=None, gt=0, le=120)
    weekly_volume_km: float = Field(ge=0, le=300, description="Usual km/week, last 8-12 weeks")
    peak_volume_km: float | None = Field(default=None, ge=0, le=300)

    target_race_name: str | None = Field(default=None, max_length=160)
    target_race_date: date | None = None
    target_race_distance_m: int | None = Field(default=None, gt=0)
    target_race_time_s: int | None = Field(default=None, gt=0)
    target_race_surface: Surface | None = None
    target_race_elevation_gain_m: int | None = Field(default=None, ge=0)

    preferred_slot: TrainingSlot
    available_days: list[Weekday] = Field(min_length=1)
    work_type: WorkType
    avg_sleep_hours: float | None = Field(default=None, ge=0, le=14)
    terrain_access: list[Surface] = Field(min_length=1)
    default_run_surface: RunSurfaceDefault | None = None
    methodology: Methodology = Methodology.TRADITIONAL
    double_sessions_ok: bool
    long_run_day: Weekday | None = None
    strength_sessions_per_week: int = Field(ge=0, le=7)
    strength_setting: StrengthSetting
    hr_sensor: HrSensor | None = None
    injury_notes: str | None = Field(default=None, max_length=1000)
    coach_notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _hr_consistency(self) -> Self:
        rest, thr, mx = self.resting_hr, self.threshold_hr, self.max_hr
        if rest and thr and rest >= thr:
            raise ValueError("resting_hr must be lower than threshold_hr")
        if thr and mx and thr >= mx:
            raise ValueError("threshold_hr must be lower than max_hr")
        return self


class ProfileCreate(_ProfileFields):
    intervals_athlete_id: str | None = Field(default=None, pattern=INTERVALS_ATHLETE_ID_PATTERN)
    # Write-only: encrypted before persistence, never returned by the API
    intervals_api_key: SecretStr | None = None

    @model_validator(mode="after")
    def _intervals_pair(self) -> Self:
        if bool(self.intervals_athlete_id) != bool(self.intervals_api_key):
            raise ValueError("intervals_athlete_id and intervals_api_key must be provided together")
        return self


class ProfileUpdate(StrictModel):
    """Partial update: every field optional."""

    background: AthleteBackground | None = None
    weight_kg: float | None = Field(default=None, gt=0)
    threshold_hr: int | None = Field(default=None, gt=0, le=230)
    max_hr: int | None = Field(default=None, gt=0, le=240)
    resting_hr: int | None = Field(default=None, gt=0, le=120)
    weekly_volume_km: float | None = Field(default=None, ge=0, le=300)
    peak_volume_km: float | None = Field(default=None, ge=0, le=300)
    target_race_name: str | None = Field(default=None, max_length=160)
    target_race_date: date | None = None
    target_race_distance_m: int | None = Field(default=None, gt=0)
    target_race_time_s: int | None = Field(default=None, gt=0)
    target_race_surface: Surface | None = None
    double_sessions_ok: bool | None = None
    long_run_day: Weekday | None = None
    strength_sessions_per_week: int | None = Field(default=None, ge=0, le=7)
    strength_setting: StrengthSetting | None = None
    hr_sensor: HrSensor | None = None
    injury_notes: str | None = Field(default=None, max_length=1000)
    coach_notes: str | None = Field(default=None, max_length=2000)
    preferred_slot: TrainingSlot | None = None
    available_days: list[Weekday] | None = Field(default=None, min_length=1)
    work_type: WorkType | None = None
    avg_sleep_hours: float | None = Field(default=None, ge=0, le=14)
    terrain_access: list[Surface] | None = Field(default=None, min_length=1)
    default_run_surface: RunSurfaceDefault | None = None
    methodology: Methodology | None = None
    intervals_athlete_id: str | None = Field(default=None, pattern=INTERVALS_ATHLETE_ID_PATTERN)
    intervals_api_key: SecretStr | None = None


class ProfileRead(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    background: AthleteBackground
    birth_year: int | None
    weight_kg: float | None
    threshold_hr: int | None
    max_hr: int | None
    resting_hr: int | None
    weekly_volume_km: float | None
    peak_volume_km: float | None
    target_race_name: str | None
    target_race_date: date | None
    target_race_distance_m: int | None
    target_race_time_s: int | None
    target_race_surface: Surface | None
    target_race_elevation_gain_m: int | None
    preferred_slot: TrainingSlot
    available_days: list[Weekday]
    work_type: WorkType
    avg_sleep_hours: float | None
    terrain_access: list[Surface]
    default_run_surface: Surface | None
    methodology: Methodology
    double_sessions_ok: bool
    long_run_day: Weekday | None
    strength_sessions_per_week: int
    strength_setting: StrengthSetting
    hr_sensor: HrSensor | None
    injury_notes: str | None
    coach_notes: str | None
    intervals_athlete_id: str | None
    intervals_connected: bool  # derived; the API key itself is never exposed
    intervals_synced_at: datetime | None
    updated_at: datetime | None


class OnboardingPayload(StrictModel):
    """Single submit of the /onboarding wizard."""

    display_name: str | None = Field(default=None, max_length=120)
    timezone: str = Field(default="Europe/Rome", max_length=64)
    profile: ProfileCreate
    personal_bests: list[PersonalBestCreate] = Field(default_factory=list)
