from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import col, select

from app.agents.context import MissingProfileError, active_plan, local_today
from app.agents.llm import AgentError, LLMClient, get_llm
from app.agents.training_periodization import NoActivePlanError, adjust_plan, generate_plan
from app.api.deps import CurrentUser, SessionDep
from app.api.errors import agent_http_error
from app.models import Workout
from app.models.enums import AgentTrigger
from app.schemas.coach import (
    PlanAdjustApply,
    PlanAdjustResult,
    PlanGenerateRequest,
    PlanGenerateResult,
)
from app.schemas.training import TrainingPlanRead, WorkoutRead

router = APIRouter(tags=["plans"])

LLMDep = Annotated[LLMClient, Depends(get_llm)]


@router.post("/plans/generate", response_model=PlanGenerateResult, status_code=201)
async def generate(
    user: CurrentUser,
    session: SessionDep,
    llm: LLMDep,
    body: PlanGenerateRequest | None = None,
) -> PlanGenerateResult:
    """Onboarding → TrainingPeriodizationAgent. Archives the previous active plan."""
    try:
        plan, workouts, log = await generate_plan(
            session, llm, user, start_date=body.start_date if body else None
        )
    except (AgentError, MissingProfileError) as exc:
        raise agent_http_error(exc) from exc
    return PlanGenerateResult(
        plan=TrainingPlanRead.model_validate(plan),
        workouts=[WorkoutRead.model_validate(w) for w in workouts],
        agent_run_id=log.id,
    )


@router.get("/plans/active", response_model=TrainingPlanRead)
async def read_active(user: CurrentUser, session: SessionDep) -> TrainingPlanRead:
    plan = await active_plan(session, user.id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No active plan")
    return TrainingPlanRead.model_validate(plan)


@router.get("/workouts", response_model=list[WorkoutRead])
async def list_workouts(
    user: CurrentUser,
    session: SessionDep,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
) -> list[WorkoutRead]:
    """Calendar view of the active plan (default: current week Mon-Sun)."""
    plan = await active_plan(session, user.id)
    if plan is None:
        return []
    today = local_today(user)
    start = start or today - timedelta(days=today.weekday())
    end = end or start + timedelta(days=6)
    stmt = (
        select(Workout)
        .where(
            Workout.plan_id == plan.id,
            col(Workout.scheduled_date) >= start,
            col(Workout.scheduled_date) <= end,
        )
        .order_by(col(Workout.scheduled_date), col(Workout.session_slot))
    )
    return [WorkoutRead.model_validate(w) for w in (await session.exec(stmt)).all()]


@router.post("/plans/adjust", response_model=PlanAdjustResult)
async def apply_adjustment(
    body: PlanAdjustApply, user: CurrentUser, session: SessionDep, llm: LLMDep
) -> PlanAdjustResult:
    """Applies an adjustment proposed by the coach chat, after the athlete confirms it."""
    try:
        adjusted = await adjust_plan(
            session,
            llm,
            user,
            request=body.adjustment,
            trigger=AgentTrigger.CHAT,
            after=local_today(user) - timedelta(days=1),  # today is adjustable too
        )
    except (AgentError, MissingProfileError, NoActivePlanError) as exc:
        raise agent_http_error(exc) from exc
    if adjusted is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No upcoming workouts in that window")
    modified, output, log = adjusted
    return PlanAdjustResult(
        modified=[WorkoutRead.model_validate(w) for w in modified],
        rationale=output.rationale,
        agent_run_id=log.id,
    )
