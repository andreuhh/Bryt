"""Agent execution log exposure and alpha-tester feedback."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.models.enums import AgentName, AgentRunStatus, AgentTrigger, Feedback
from app.schemas.agents import MechanicalLoadOutput, NutritionRecoveryOutput, PlanAdjustmentOutput
from app.schemas.common import ORMModel, StrictModel


class AgentFeedbackCreate(StrictModel):
    feedback: Feedback
    comment: str | None = Field(default=None, max_length=2000)


class AgentExecutionLogRead(ORMModel):
    """Note: input_snapshot is deliberately not exposed."""

    id: uuid.UUID
    agent_name: AgentName
    trigger: AgentTrigger
    pipeline_run_id: uuid.UUID
    status: AgentRunStatus
    activity_id: uuid.UUID | None
    plan_id: uuid.UUID | None
    output: dict[str, Any] | None
    error: str | None
    model: str
    feedback: Feedback | None
    feedback_comment: str | None
    created_at: datetime | None


class _TypedRun(StrictModel):
    """One agent run in a report, with its output parsed into the agent's schema."""

    id: uuid.UUID
    status: AgentRunStatus
    error: str | None
    model: str
    feedback: Feedback | None
    feedback_comment: str | None
    created_at: datetime | None


class MechanicalLoadRun(_TypedRun):
    output: MechanicalLoadOutput | None


class PlanAdjustmentRun(_TypedRun):
    output: PlanAdjustmentOutput | None


class NutritionRecoveryRun(_TypedRun):
    output: NutritionRecoveryOutput | None


class ActivityReport(StrictModel):
    """Latest pipeline run for an activity: the three agent outputs (any may be missing)."""

    activity_id: uuid.UUID
    pipeline_run_id: uuid.UUID | None
    analyses_left: int = Field(description="Analyses the athlete can still request (cost cap)")
    mechanical_load: MechanicalLoadRun | None = None
    plan_adjustment: PlanAdjustmentRun | None = None
    nutrition_recovery: NutritionRecoveryRun | None = None
