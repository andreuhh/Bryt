"""Structured outputs of the three agents — the Shared State contract.

Each model is passed to the Anthropic SDK as the output schema and the validated result is
persisted in AgentExecutionLog.output. Agents interpret numbers computed by services; they
never invent physiological thresholds.
"""

import uuid
from datetime import date
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from app.models.enums import Methodology, Severity
from app.schemas.common import StrictModel
from app.schemas.training import PlanBlock, WorkoutDraft


class LoadLevel(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class AlertCode(StrEnum):
    MECHANICAL_BREAKDOWN = "MECHANICAL_BREAKDOWN"  # cadence drop with stable HR
    CARDIAC_DRIFT = "CARDIAC_DRIFT"
    EXCESSIVE_MECHANICAL_LOAD = "EXCESSIVE_MECHANICAL_LOAD"
    PACE_SPIKE = "PACE_SPIKE"  # speed jump vs athlete history
    SURFACE_TRANSITION = "SURFACE_TRANSITION"  # e.g. trail runner on fast asphalt
    PLAN_DEVIATION = "PLAN_DEVIATION"
    CONTEXTUAL_HR_ANOMALY = "CONTEXTUAL_HR_ANOMALY"  # explained by caffeine/jet lag/sleep
    UNDER_RECOVERY = "UNDER_RECOVERY"


class ContextFactor(StrEnum):
    CAFFEINE = "CAFFEINE"
    JET_LAG = "JET_LAG"
    TRAVEL = "TRAVEL"
    SLEEP = "SLEEP"
    STRESS = "STRESS"
    HEAT = "HEAT"
    ILLNESS = "ILLNESS"
    OTHER = "OTHER"


class Readiness(StrEnum):
    READY = "READY"
    CAUTION = "CAUTION"
    REST = "REST"


# --- TrainingPeriodizationAgent ---------------------------------------------------------


class PlanSkeletonOutput(StrictModel):
    """Phase 1 of plan generation: periodization only (blocks and weeks, no workouts)."""

    plan_name: str = Field(max_length=160)
    methodology: Methodology
    goal_summary: str
    start_date: date
    end_date: date
    blocks: list[PlanBlock] = Field(min_length=1)
    rationale: str


class BlockWorkoutsOutput(StrictModel):
    """Phase 2: every day of ONE block (REST days explicit)."""

    workouts: list[WorkoutDraft] = Field(min_length=1)


class ConfirmedWorkout(StrictModel):
    workout_id: uuid.UUID
    workout: WorkoutDraft = Field(description="Full detail: structure with calibrated pace/HR")


class KeySessionProposal(StrictModel):
    workout_id: uuid.UUID
    proposed: WorkoutDraft
    reason: str


class RefinementOutput(StrictModel):
    """Weekly refinement: provisional → confirmed for the next 2 weeks, plus proposals
    (never applied automatically) for key sessions further ahead."""

    confirmed: list[ConfirmedWorkout]
    key_session_proposals: list[KeySessionProposal] = Field(default_factory=list)
    notes: str = Field(description="Short summary for the athlete, in Italian")


class WorkoutAdjustmentAction(StrEnum):
    KEEP = "KEEP"
    REPLACE = "REPLACE"
    REDUCE = "REDUCE"
    REST = "REST"


class WorkoutAdjustment(StrictModel):
    workout_id: uuid.UUID
    action: WorkoutAdjustmentAction
    new_workout: WorkoutDraft | None = None
    reason: str

    @model_validator(mode="after")
    def _needs_replacement(self) -> Self:
        needs = self.action in (WorkoutAdjustmentAction.REPLACE, WorkoutAdjustmentAction.REDUCE)
        if needs and self.new_workout is None:
            raise ValueError(f"action {self.action} requires new_workout")
        return self


class PlanAdjustmentOutput(StrictModel):
    """Re-modulation of the next 3-4 days after a MechanicalLoadAgent trigger."""

    adjustments: list[WorkoutAdjustment] = Field(min_length=1, max_length=8)
    rationale: str


# --- MechanicalLoadAgent ----------------------------------------------------------------


class ExecutionCompliance(StrictModel):
    workout_id: uuid.UUID | None = None
    compliance_score: int = Field(ge=0, le=100)
    pace_deviation_pct: float | None = None
    hr_deviation_pct: float | None = None
    notes: str


class MechanicalLoadAssessment(StrictModel):
    load_level: LoadLevel
    load_score: int = Field(ge=0, le=100, description="Relative to the athlete's own history")
    surface_factor: float = Field(gt=0, description="1.0 = athlete's habitual surface")
    speed_increase_vs_history_pct: float | None = None
    eccentric_stress: LoadLevel
    muscle_groups: list[str] = Field(default_factory=list)
    explanation: str


class CadenceHrDivergence(StrictModel):
    detected: bool
    final_segment_start_pct: float | None = Field(default=None, ge=0, le=100)
    cadence_drop_spm: float | None = None
    hr_change_bpm: float | None = None
    ground_contact_increase_ms: float | None = None
    interpretation: str


class ContextualFactorAssessment(StrictModel):
    factor: ContextFactor
    estimated_hr_impact_bpm: float | None = None
    explanation: str


class Alert(StrictModel):
    code: AlertCode
    severity: Severity
    title: str = Field(max_length=120)
    message: str


class PlanAdjustmentRequest(StrictModel):
    reason: str
    days_affected: int = Field(ge=1, le=4)
    guidance: str = Field(description="What the TrainingPeriodizationAgent should change")


class MechanicalLoadOutput(StrictModel):
    summary: str
    execution: ExecutionCompliance
    mechanical_load: MechanicalLoadAssessment
    cadence_hr_divergence: CadenceHrDivergence
    contextual_factors: list[ContextualFactorAssessment] = Field(default_factory=list)
    false_alarm_suppressed: bool = Field(
        description="True when an HR anomaly is explained by context, not loss of form"
    )
    alerts: list[Alert] = Field(default_factory=list)
    plan_adjustment_needed: bool
    adjustment_request: PlanAdjustmentRequest | None = None

    @model_validator(mode="after")
    def _adjustment_consistency(self) -> Self:
        if self.plan_adjustment_needed and self.adjustment_request is None:
            raise ValueError("plan_adjustment_needed=true requires adjustment_request")
        if not self.plan_adjustment_needed and self.adjustment_request is not None:
            raise ValueError("adjustment_request given but plan_adjustment_needed=false")
        return self


# --- NutritionRecoveryAgent (bipartite output) ------------------------------------------


class PostSessionFueling(StrictModel):
    window_minutes: int = Field(ge=0, le=240)
    carbs_g: float = Field(ge=0)
    protein_g: float = Field(ge=0)


class Electrolytes(StrictModel):
    sodium_mg: int = Field(ge=0)
    fluids_ml: int = Field(ge=0)
    notes: str | None = None


class CaffeineTiming(StrictModel):
    recommended: bool
    dose_mg_per_kg: float | None = Field(default=None, ge=0, le=6)
    minutes_before_session: int | None = Field(default=None, ge=0, le=240)
    cutoff_local_time: str | None = Field(
        default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="HH:MM, protects sleep"
    )
    notes: str | None = None


class NutritionProtocol(StrictModel):
    daily_carbs_g_per_kg: float = Field(ge=0, le=15)
    daily_protein_g_per_kg: float = Field(ge=0, le=4)
    post_session: PostSessionFueling
    electrolytes: Electrolytes
    caffeine: CaffeineTiming
    next_session_fueling: str | None = None
    notes: list[str] = Field(default_factory=list)


class SleepGuidance(StrictModel):
    target_hours: float = Field(ge=0, le=14)
    bedtime_local: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    notes: str | None = None


class MobilityItem(StrictModel):
    name: str
    duration_min: int = Field(ge=1, le=120)
    focus: str


class JetLagGuidance(StrictModel):
    strategy: str
    light_exposure: str | None = None
    notes: str | None = None


class RecoveryProtocol(StrictModel):
    readiness_next_session: Readiness
    sleep: SleepGuidance
    mobility: list[MobilityItem] = Field(default_factory=list)
    jet_lag: JetLagGuidance | None = None
    stress_management: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class NutritionRecoveryOutput(StrictModel):
    summary: str
    nutrition_protocol: NutritionProtocol
    recovery_protocol: RecoveryProtocol


# --- Coach chat -------------------------------------------------------------------------


class CoachChatOutput(StrictModel):
    reply: str = Field(description="Answer to the athlete, in Italian, conversational")
    proposed_adjustment: PlanAdjustmentRequest | None = Field(
        default=None,
        description="Only when the athlete asks for (or clearly needs) a change to the plan. "
        "Never applied automatically: the athlete confirms it in the UI.",
    )
