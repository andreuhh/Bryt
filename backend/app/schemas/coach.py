"""API contracts for plan generation/adjustment and the coach chat."""

import uuid
from datetime import date
from typing import Literal

from pydantic import Field

from app.schemas.agents import PlanAdjustmentRequest
from app.schemas.common import StrictModel
from app.schemas.training import TrainingPlanRead, WorkoutRead


class PlanGenerateRequest(StrictModel):
    start_date: date | None = Field(default=None, description="Default: tomorrow")


class PlanGenerateResult(StrictModel):
    plan: TrainingPlanRead
    workouts: list[WorkoutRead]
    agent_run_id: uuid.UUID


class PlanAdjustApply(StrictModel):
    """Confirms an adjustment proposed by the coach chat."""

    adjustment: PlanAdjustmentRequest


class PlanAdjustResult(StrictModel):
    modified: list[WorkoutRead]
    rationale: str
    agent_run_id: uuid.UUID


class ChatMessage(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(StrictModel):
    """Stateless: the client sends the visible conversation (last turn = user)."""

    messages: list[ChatMessage] = Field(min_length=1, max_length=40)


class ChatResponse(StrictModel):
    reply: str
    proposed_adjustment: PlanAdjustmentRequest | None
    agent_run_id: uuid.UUID
