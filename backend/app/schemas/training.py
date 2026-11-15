"""Calibration, plan structure and workouts.

Shapes stored in JSONB columns (TrainingPlan.blocks, Workout.structure) are defined here.
"""

import uuid
from datetime import date, datetime
from typing import Self

from pydantic import Field, model_validator

from app.models.enums import (
    BlockPhase,
    Methodology,
    PlanStatus,
    SessionSlot,
    StepKind,
    WeekLoadType,
    WorkoutStatus,
    WorkoutType,
)
from app.schemas.common import HrRange, ORMModel, PaceRange, StrictModel

# --- Deterministic calibration (computed by services, input to agents) ------------------


class TrainingZone(StrictModel):
    code: str = Field(description="Zone identifier, e.g. 'Z1'..'Z5', 'LT1', 'LT2'")
    label: str
    hr: HrRange | None = None
    pace: PaceRange | None = None


class AthleteCalibration(StrictModel):
    """Zones and thresholds derived from recent PBs, threshold HR and background."""

    threshold_pace_s_per_km: float | None = Field(default=None, gt=0)
    threshold_hr: int | None = Field(default=None, gt=0)
    zones: list[TrainingZone]
    source_notes: str = Field(description="Which PBs / tests the calibration was derived from")


# --- Plan structure (JSONB) -------------------------------------------------------------


class PlanWeek(StrictModel):
    week_index: int = Field(ge=1)
    start_date: date
    load_type: WeekLoadType
    target_volume_km: float | None = Field(default=None, ge=0)
    focus: str | None = None


class PlanBlock(StrictModel):
    name: str
    phase: BlockPhase
    start_date: date
    end_date: date
    objective: str
    weeks: list[PlanWeek] = Field(min_length=1)

    @model_validator(mode="after")
    def _dates(self) -> Self:
        if self.start_date > self.end_date:
            raise ValueError("block start_date must be <= end_date")
        return self


class WorkoutStep(StrictModel):
    kind: StepKind
    repeat: int = Field(default=1, ge=1)
    duration_s: int | None = Field(default=None, gt=0)
    distance_m: int | None = Field(default=None, gt=0)
    target_zone: str | None = Field(default=None, description="TrainingZone.code")
    target_pace: PaceRange | None = None
    target_hr: HrRange | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _has_length(self) -> Self:
        if self.duration_s is None and self.distance_m is None:
            raise ValueError("step needs duration_s or distance_m")
        return self


class WorkoutDraft(StrictModel):
    """A workout as proposed by the TrainingPeriodizationAgent (not yet persisted)."""

    scheduled_date: date
    session_slot: SessionSlot = SessionSlot.SINGLE
    workout_type: WorkoutType
    title: str = Field(max_length=160)
    description: str | None = None
    target_duration_s: int | None = Field(default=None, gt=0)
    target_distance_m: int | None = Field(default=None, gt=0)
    structure: list[WorkoutStep] = Field(default_factory=list)


# --- API read models --------------------------------------------------------------------


class WorkoutRead(ORMModel):
    id: uuid.UUID
    plan_id: uuid.UUID
    scheduled_date: date
    session_slot: SessionSlot
    workout_type: WorkoutType
    status: WorkoutStatus
    title: str
    description: str | None
    target_duration_s: int | None
    target_distance_m: int | None
    structure: list[WorkoutStep]
    original_snapshot: WorkoutDraft | None
    modification_reason: str | None
    activity_id: uuid.UUID | None


class TrainingPlanRead(ORMModel):
    id: uuid.UUID
    name: str
    status: PlanStatus
    methodology: Methodology
    start_date: date
    end_date: date
    goal_summary: str | None
    blocks: list[PlanBlock]
    rationale: str | None
    created_at: datetime | None
