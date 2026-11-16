"""Activities, contextual tags and time series."""

import uuid
from datetime import datetime

from pydantic import Field

from app.models.enums import ActivitySource, Surface
from app.schemas.common import ORMModel, StrictModel


class ContextTags(StrictModel):
    """External factors that prevent false 'loss of form' alarms (Activity.context_tags)."""

    caffeine_mg: int | None = Field(default=None, ge=0, le=1000)
    caffeine_minutes_before: int | None = Field(default=None, ge=0, le=600)
    jet_lag_hours: int | None = Field(
        default=None, ge=-12, le=14, description="Time-zone shift vs home in the last 72h"
    )
    travelled_last_48h: bool = False
    sleep_hours_prev_night: float | None = Field(default=None, ge=0, le=14)
    sleep_quality: int | None = Field(default=None, ge=1, le=5)
    stress_level: int | None = Field(default=None, ge=1, le=5)
    rpe: int | None = Field(default=None, ge=1, le=10, description="Perceived effort")
    heat: bool = False
    feeling_unwell: bool = False
    notes: str | None = Field(default=None, max_length=1000)


class SegmentStats(StrictModel):
    """Medians over one segment of the run (moving samples only)."""

    start_s: float
    end_s: float
    samples: int
    cadence_spm: float | None
    heart_rate: float | None
    pace_s_per_km: float | None
    ground_contact_ms: float | None
    stride_length_m: float | None = None


class CadenceHrDivergenceMetrics(StrictModel):
    """Deterministic 'Cadence vs HR Divergence' (stored in Activity.computed_metrics).

    mechanical_breakdown = in the final segment cadence drops > threshold, GCT rises or stride
    length collapses, while HR stays stable — muscular failure without cardiac drift.
    """

    evaluated: bool
    reason: str | None = None
    session_profile: str | None = Field(default=None, description="'steady' or 'variable'")
    baseline: SegmentStats | None = None
    final: SegmentStats | None = None
    cadence_drop_spm: float | None = None
    hr_change_bpm: float | None = None
    hr_change_pct: float | None = None
    pace_change_pct: float | None = Field(default=None, description="> 0 = slower in the final")
    ground_contact_change_pct: float | None = None
    hr_stable: bool | None = None
    hr_in_target_zone: bool | None = None
    cadence_drop_detected: bool = False
    ground_contact_rise_detected: bool = False
    stride_length_change_pct: float | None = Field(default=None, description="< 0 = shorter")
    stride_length_drop_detected: bool = False
    mechanical_breakdown: bool = False


class ComputedMetrics(StrictModel):
    moving_time_s: float | None = None
    speed_cv: float | None = Field(default=None, description="Coefficient of variation of speed")
    aerobic_decoupling_pct: float | None = Field(
        default=None, description="Speed/HR efficiency loss 1st vs 2nd half (Pa:Hr)"
    )
    cadence_hr_divergence: CadenceHrDivergenceMetrics


class ActivityContextUpdate(StrictModel):
    """Payload of the post-activity quick-tag modal."""

    surface: Surface | None = None
    context_tags: ContextTags


class ActivityRead(ORMModel):
    id: uuid.UUID
    source: ActivitySource
    external_id: str | None
    name: str | None
    sport: str
    start_time: datetime
    duration_s: int
    moving_time_s: int | None
    distance_m: float
    avg_pace_s_per_km: float | None
    avg_hr: float | None
    max_hr: float | None
    avg_cadence_spm: float | None
    avg_ground_contact_ms: float | None
    elevation_gain_m: float | None
    elevation_loss_m: float | None
    computed_metrics: ComputedMetrics
    surface: Surface | None
    context_tags: ContextTags


class ActivityStreamRead(ORMModel):
    activity_id: uuid.UUID
    sample_count: int
    elapsed_s: list[float]
    distance_m: list[float | None]
    pace_s_per_km: list[float | None]
    heart_rate: list[float | None]
    cadence_spm: list[float | None]
    elevation_m: list[float | None]
    ground_contact_ms: list[float | None]
