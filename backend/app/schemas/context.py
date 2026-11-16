"""Deterministic context handed to the agents (computed by services, never by the LLM)."""

import datetime

from pydantic import Field

from app.models.enums import DataCoverage
from app.schemas.common import StrictModel


class RecentRace(StrictModel):
    """A race in the last weeks (result logged as PB/race, or a completed RACE workout)."""

    date: datetime.date
    days_ago: int
    distance_m: int
    name: str | None = None
    recovery_until: datetime.date = Field(
        description="End of the expected post-race recovery (about one day per mile raced)"
    )


class TrainingBaseline(StrictModel):
    """The athlete's recent history: the yardstick for 'relative' load and speed."""

    window_days: int
    data_coverage: DataCoverage = Field(
        description="Judged on the habitual window: LOW = recorded history does not reflect "
        "the real volume (use declared); HIGH = recordings are complete, so a low recent "
        "volume is real (taper, race, recovery, break), not missing data"
    )
    declared_weekly_km: float | None = None
    effective_weekly_km: float | None = Field(
        default=None,
        description="Current volume to plan from (recent recorded; declared when coverage is LOW)",
    )
    habitual_window_days: int
    habitual_weekly_km: float = Field(
        description="Recorded weekly average over the habitual window (longer than window_days)"
    )
    weekly_km: list[float] = Field(
        default_factory=list,
        description="Recorded km per 7-day period over the habitual window, oldest first",
    )
    recent_races: list[RecentRace] = Field(default_factory=list)
    in_post_race_recovery: bool = Field(
        default=False,
        description="A recent race's recovery window is still open: low volume and easy "
        "efforts are expected, not a loss of form",
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
