"""Audit trail of every agent execution + alpha-tester feedback."""

import uuid
from typing import Any

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import IdMixin, TenantMixin, TimestampMixin, enum_column, jsonb_column
from app.models.enums import AgentName, AgentRunStatus, AgentTrigger, Feedback


class AgentExecutionLog(IdMixin, TimestampMixin, TenantMixin, table=True):
    __tablename__ = "agent_execution_logs"
    __table_args__ = (
        Index("ix_agent_log_run", "pipeline_run_id"),
        Index("ix_agent_log_user_agent", "user_id", "agent_name"),
    )

    agent_name: AgentName = Field(sa_column=enum_column(AgentName))
    trigger: AgentTrigger = Field(sa_column=enum_column(AgentTrigger))
    # Groups the cascade MechanicalLoad → (Periodization) → NutritionRecovery
    pipeline_run_id: uuid.UUID
    status: AgentRunStatus = Field(sa_column=enum_column(AgentRunStatus))

    activity_id: uuid.UUID | None = Field(
        default=None, foreign_key="activities.id", index=True, ondelete="SET NULL"
    )
    plan_id: uuid.UUID | None = Field(
        default=None, foreign_key="training_plans.id", ondelete="SET NULL"
    )

    input_snapshot: dict[str, Any] = Field(default_factory=dict, sa_column=jsonb_column())
    output: dict[str, Any] | None = Field(default=None, sa_column=jsonb_column(nullable=True))
    error: str | None = None

    model: str = Field(max_length=64)
    # Billed separately: uncached input, cache writes (~1.25x), cache reads (~0.1x), output
    input_tokens: int | None = Field(default=None, ge=0)
    cache_creation_input_tokens: int | None = Field(default=None, ge=0)
    cache_read_input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)

    feedback: Feedback | None = Field(default=None, sa_column=enum_column(Feedback, nullable=True))
    feedback_comment: str | None = Field(default=None, max_length=2000)
