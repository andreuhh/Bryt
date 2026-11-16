"""Deterministic context handed to the agents (computed by services, never by the LLM)."""

from pydantic import Field

from app.models.enums import DataCoverage
from app.schemas.common import StrictModel


class TrainingBaseline(StrictModel):
    """The athlete's recent history: the yardstick for 'relative' load and speed."""

    window_days: int
    data_coverage: DataCoverage = Field(
        description="LOW = recorded history does not reflect the real volume: use declared"
    )
    declared_weekly_km: float | None = None
    effective_weekly_km: float | None = Field(
        default=None, description="Volume to plan from (declared when coverage is LOW)"
    )
    activities: int
    total_km: float
    weekly_avg_km: float
    acute_7d_km: float
    acute_chronic_ratio: float | None = Field(
        default=None, description="7-day km / (28-day km / 4); > 1.3 = sharp load increase"
    )
    avg_pace_s_per_km: float | None = None
    fastest_avg_pace_s_per_km: float | None = None
    avg_cadence_spm: float | None = None
    longest_run_km: float | None = None
    total_elevation_loss_m: float | None = None
    km_by_surface: dict[str, float] = Field(default_factory=dict)


class ElevationQuality(StrictModel):
    reliable: bool | None
    reason: str
