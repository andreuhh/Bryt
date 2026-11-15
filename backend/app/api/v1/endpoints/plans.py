import uuid
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents.context import MissingProfileError, active_plan, local_today
from app.agents.llm import AgentError, LLMClient, get_llm
from app.agents.scheduler import PlanJobLauncher, get_plan_job_launcher
from app.agents.training_periodization import (
    NoActivePlanError,
    adjust_plan,
    refine_plan,
    start_plan_generation,
)
from app.api.deps import CurrentUser, SessionDep
from app.api.errors import agent_http_error
from app.models import TrainingPlan, User, Workout, WorkoutRevision
from app.models.enums import AgentTrigger, PlanStatus, RevisionStatus
from app.schemas.coach import (
    PlanAdjustApply,
    PlanAdjustResult,
    PlanGenerateRequest,
    RefinementResult,
)
from app.schemas.training import TrainingPlanRead, WorkoutRead, WorkoutRevisionRead
from app.services.workouts import ProposalNotApplicableError, history, resolve_proposal

router = APIRouter(tags=["plans"])

LLMDep = Annotated[LLMClient, Depends(get_llm)]


async def _active_or_404(session: AsyncSession, user: User) -> TrainingPlan:
    plan = await active_plan(session, user.id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No active plan")
    return plan


# --- Generation ---------------------------------------------------------------------------


@router.post("/plans/generate", response_model=TrainingPlanRead, status_code=202)
async def generate(
    user: CurrentUser,
    session: SessionDep,
    background: BackgroundTasks,
    launch: Annotated[PlanJobLauncher, Depends(get_plan_job_launcher)],
    body: PlanGenerateRequest | None = None,
) -> TrainingPlanRead:
    """Starts the TrainingPeriodizationAgent in background. Poll GET /plans/{id} until
    status is ACTIVE (or FAILED: see generation_error). The previous plan stays active
    until the new one is complete."""
    generating = (
        await session.exec(
            select(TrainingPlan).where(
                TrainingPlan.user_id == user.id, TrainingPlan.status == PlanStatus.GENERATING
            )
        )
    ).first()
    if generating is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A plan is already being generated")
    try:
        plan = await start_plan_generation(
            session, user, start_date=body.start_date if body else None
        )
    except MissingProfileError as exc:
        raise agent_http_error(exc) from exc
    background.add_task(launch, user.id, plan.id)
    return TrainingPlanRead.model_validate(plan)


@router.get("/plans/active", response_model=TrainingPlanRead)
async def read_active(user: CurrentUser, session: SessionDep) -> TrainingPlanRead:
    return TrainingPlanRead.model_validate(await _active_or_404(session, user))


@router.get("/plans/active/proposals", response_model=list[WorkoutRevisionRead])
async def list_proposals(user: CurrentUser, session: SessionDep) -> list[WorkoutRevisionRead]:
    """Key-session changes waiting for the athlete's decision."""
    plan = await _active_or_404(session, user)
    stmt = (
        select(WorkoutRevision)
        .where(WorkoutRevision.plan_id == plan.id, WorkoutRevision.status == RevisionStatus.PENDING)
        .order_by(col(WorkoutRevision.created_at))
    )
    return [WorkoutRevisionRead.model_validate(r) for r in (await session.exec(stmt)).all()]


@router.post("/plans/active/refine", response_model=RefinementResult)
async def refine_now(user: CurrentUser, session: SessionDep, llm: LLMDep) -> RefinementResult:
    """Manual trigger of the weekly refinement (normally Sunday evening, automatic)."""
    try:
        confirmed, proposals, output = await refine_plan(session, llm, user)
    except (AgentError, MissingProfileError, NoActivePlanError) as exc:
        raise agent_http_error(exc) from exc
    return RefinementResult(
        confirmed=[WorkoutRead.model_validate(w) for w in confirmed],
        proposals=[WorkoutRevisionRead.model_validate(p) for p in proposals],
        notes=output.notes if output else None,
    )


@router.get("/plans/{plan_id}", response_model=TrainingPlanRead)
async def read_plan(plan_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> TrainingPlanRead:
    plan = await session.get(TrainingPlan, plan_id)
    if plan is None or plan.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found")
    return TrainingPlanRead.model_validate(plan)


# --- Proposals ----------------------------------------------------------------------------


async def _resolve(
    revision_id: uuid.UUID, user: User, session: AsyncSession, *, accept: bool
) -> Workout:
    revision = await session.get(WorkoutRevision, revision_id)
    if revision is None or revision.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proposal not found")
    try:
        return await resolve_proposal(session, revision, accept=accept, today=local_today(user))
    except ProposalNotApplicableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/plans/proposals/{revision_id}/accept", response_model=WorkoutRead)
async def accept_proposal(
    revision_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> WorkoutRead:
    return WorkoutRead.model_validate(await _resolve(revision_id, user, session, accept=True))


@router.post("/plans/proposals/{revision_id}/reject", response_model=WorkoutRead)
async def reject_proposal(
    revision_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> WorkoutRead:
    return WorkoutRead.model_validate(await _resolve(revision_id, user, session, accept=False))


# --- Calendar -----------------------------------------------------------------------------


@router.get("/workouts", response_model=list[WorkoutRead])
async def list_workouts(
    user: CurrentUser,
    session: SessionDep,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
    key_only: bool = False,
) -> list[WorkoutRead]:
    """Calendar of the active plan. Default: current week (Mon-Sun); with key_only=true the
    default range is the whole plan ('where are my long runs')."""
    plan = await active_plan(session, user.id)
    if plan is None:
        return []
    if key_only:
        start, end = start or plan.start_date, end or plan.end_date
    else:
        today = local_today(user)
        start = start or today - timedelta(days=today.weekday())
        end = end or start + timedelta(days=6)
    stmt = select(Workout).where(
        Workout.plan_id == plan.id,
        col(Workout.scheduled_date) >= start,
        col(Workout.scheduled_date) <= end,
    )
    if key_only:
        stmt = stmt.where(col(Workout.is_key_session).is_(True))
    stmt = stmt.order_by(col(Workout.scheduled_date), col(Workout.session_slot))
    return [WorkoutRead.model_validate(w) for w in (await session.exec(stmt)).all()]


@router.get("/workouts/{workout_id}/history", response_model=list[WorkoutRevisionRead])
async def workout_history(
    workout_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[WorkoutRevisionRead]:
    """Why and when a session changed (applied changes, proposals and their outcome)."""
    workout = await session.get(Workout, workout_id)
    if workout is None or workout.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workout not found")
    return [WorkoutRevisionRead.model_validate(r) for r in await history(session, workout_id)]


# --- Adjustment confirmed from the coach chat ---------------------------------------------


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
