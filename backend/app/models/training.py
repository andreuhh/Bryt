"""Periodized training plans and their workouts."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import IdMixin, TenantMixin, TimestampMixin, enum_column, jsonb_column
from app.models.enums import Methodology, PlanStatus, SessionSlot, WorkoutStatus, WorkoutType


class TrainingPlan(IdMixin, TimestampMixin, TenantMixin, table=True):
    __tablename__ = "training_plans"

    name: str = Field(max_length=160)
    status: PlanStatus = Field(default=PlanStatus.DRAFT, sa_column=enum_column(PlanStatus))
    methodology: Methodology = Field(sa_column=enum_column(Methodology))
    start_date: date
    end_date: date
    goal_summary: str | None = Field(default=None, max_length=500)
    # list[PlanBlock] (app.schemas.training) — blocks with load/deload weeks
    blocks: list[dict[str, Any]] = Field(default_factory=list, sa_column=jsonb_column())
    rationale: str | None = None


class Workout(IdMixin, TimestampMixin, TenantMixin, table=True):
    __tablename__ = "workouts"
    __table_args__ = (
        Index("ix_workout_user_date", "user_id", "scheduled_date"),
        Index("ix_workout_plan_date", "plan_id", "scheduled_date"),
    )

    plan_id: uuid.UUID = Field(foreign_key="training_plans.id", ondelete="CASCADE")
    scheduled_date: date
    session_slot: SessionSlot = Field(
        default=SessionSlot.SINGLE, sa_column=enum_column(SessionSlot)
    )
    workout_type: WorkoutType = Field(sa_column=enum_column(WorkoutType))
    status: WorkoutStatus = Field(
        default=WorkoutStatus.PLANNED, sa_column=enum_column(WorkoutStatus, index=True)
    )
    title: str = Field(max_length=160)
    description: str | None = None
    target_duration_s: int | None = Field(default=None, gt=0)
    target_distance_m: int | None = Field(default=None, gt=0)
    # list[WorkoutStep] (app.schemas.training) — targets already calibrated on the athlete
    structure: list[dict[str, Any]] = Field(default_factory=list, sa_column=jsonb_column())
    # Snapshot of the workout before an agent adjustment (status MODIFIED)
    original_snapshot: dict[str, Any] | None = Field(
        default=None, sa_column=jsonb_column(nullable=True)
    )
    modification_reason: str | None = None
    activity_id: uuid.UUID | None = Field(
        default=None, foreign_key="activities.id", unique=True, ondelete="SET NULL"
    )
