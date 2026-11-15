"""TrainingPeriodizationAgent: plan generation (onboarding) and adaptive re-modulation."""

import uuid
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents import prompts
from app.agents.context import (
    active_plan,
    athlete_context,
    dump_workout,
    local_today,
    workouts_between,
)
from app.agents.llm import LLMClient
from app.agents.runner import run_agent
from app.core.config import get_settings
from app.models import AgentExecutionLog, TrainingPlan, User, Workout
from app.models.enums import (
    AgentName,
    AgentTrigger,
    PlanStatus,
    WorkoutStatus,
    WorkoutType,
)
from app.schemas.agents import (
    PlanAdjustmentOutput,
    PlanAdjustmentRequest,
    PlanGenerationOutput,
    WorkoutAdjustment,
    WorkoutAdjustmentAction,
)
from app.schemas.training import AthleteCalibration, WorkoutDraft
from app.services.history import training_baseline

WEEKDAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
DEFAULT_HORIZON_WEEKS = 12


class NoActivePlanError(Exception):
    pass


# --- Plan generation ----------------------------------------------------------------------


async def generate_plan(
    session: AsyncSession,
    llm: LLMClient,
    user: User,
    *,
    start_date: date | None = None,
    run_id: uuid.UUID | None = None,
) -> tuple[TrainingPlan, list[Workout], AgentExecutionLog]:
    today = local_today(user)
    start = start_date or today + timedelta(days=1)
    ctx, calibration = await athlete_context(session, user, today)
    race_date = ctx["athlete"].get("target_race_date")
    end = (
        date.fromisoformat(race_date)
        if race_date and date.fromisoformat(race_date) > start
        else start + timedelta(weeks=DEFAULT_HORIZON_WEEKS, days=-1)
    )
    detail_end = min(end, start + timedelta(weeks=get_settings().plan_detail_weeks, days=-1))
    baseline = await training_baseline(session, user.id, datetime.combine(today, time.min, UTC))
    ctx["baseline_28d"] = baseline.model_dump(mode="json")

    task = (
        f"Generate the training plan. start_date={start.isoformat()}, "
        f"end_date={end.isoformat()} (race day or end of block). Blocks and weeks must cover "
        f"the whole range. Day-by-day workouts ONLY from {start.isoformat()} to "
        f"{detail_end.isoformat()} inclusive (include REST days explicitly)."
    )
    available = set(ctx["athlete"]["available_days"])
    output, log = await run_agent(
        session,
        llm,
        user_id=user.id,
        agent=AgentName.TRAINING_PERIODIZATION,
        trigger=AgentTrigger.ONBOARDING,
        run_id=run_id or uuid.uuid4(),
        system=prompts.TRAINING_PERIODIZATION,
        task=task,
        context=ctx,
        output_model=PlanGenerationOutput,
        effort="high",
        max_tokens=64000,
        validate=lambda out: _plan_violations(out, start, end, detail_end, available, calibration),
    )

    for old in (
        await session.exec(
            select(TrainingPlan).where(
                TrainingPlan.user_id == user.id, TrainingPlan.status == PlanStatus.ACTIVE
            )
        )
    ).all():
        old.status = PlanStatus.ARCHIVED
        session.add(old)

    plan = TrainingPlan(
        user_id=user.id,
        name=output.plan_name,
        status=PlanStatus.ACTIVE,
        methodology=output.methodology,
        start_date=output.start_date,
        end_date=output.end_date,
        goal_summary=output.goal_summary[:500],
        blocks=[b.model_dump(mode="json") for b in output.blocks],
        rationale=output.rationale,
    )
    session.add(plan)
    await session.flush()
    workouts = [_workout_from_draft(user.id, plan.id, d) for d in output.workouts]
    session.add_all(workouts)
    log.plan_id = plan.id
    session.add(log)
    await session.commit()
    return plan, workouts, log


def _plan_violations(
    out: PlanGenerationOutput,
    start: date,
    end: date,
    detail_end: date,
    available: set[str],
    calibration: AthleteCalibration,
) -> list[str]:
    v: list[str] = []
    if out.start_date != start or out.end_date != end:
        v.append(f"plan must span exactly {start} → {end}")
    for b in out.blocks:
        if b.start_date < start or b.end_date > end:
            v.append(f"block '{b.name}' is outside {start} → {end}")
    per_day = Counter(w.scheduled_date for w in out.workouts if w.workout_type != WorkoutType.REST)
    for w in out.workouts:
        if not start <= w.scheduled_date <= detail_end:
            v.append(f"workout '{w.title}' on {w.scheduled_date} is outside {start} → {detail_end}")
        v.extend(_draft_violations(w, available, calibration))
    v.extend(f"{day}: more than 2 sessions" for day, n in per_day.items() if n > 2)
    return v


def _draft_violations(
    w: WorkoutDraft, available: set[str], calibration: AthleteCalibration
) -> list[str]:
    v: list[str] = []
    weekday = WEEKDAYS[w.scheduled_date.weekday()]
    if w.workout_type != WorkoutType.REST and weekday not in available:
        v.append(f"'{w.title}' on {w.scheduled_date} ({weekday}): not an available day")
    zones = {z.code for z in calibration.zones}
    for step in w.structure:
        if step.target_zone and step.target_zone not in zones:
            v.append(f"'{w.title}': unknown zone '{step.target_zone}' (use {sorted(zones)})")
    return v


def _workout_from_draft(user_id: uuid.UUID, plan_id: uuid.UUID, d: WorkoutDraft) -> Workout:
    return Workout(
        user_id=user_id,
        plan_id=plan_id,
        scheduled_date=d.scheduled_date,
        session_slot=d.session_slot,
        workout_type=d.workout_type,
        title=d.title,
        description=d.description,
        target_duration_s=d.target_duration_s,
        target_distance_m=d.target_distance_m,
        structure=[s.model_dump(mode="json") for s in d.structure],
    )


# --- Adaptive re-modulation ---------------------------------------------------------------


async def adjust_plan(
    session: AsyncSession,
    llm: LLMClient,
    user: User,
    *,
    request: PlanAdjustmentRequest,
    trigger: AgentTrigger,
    after: date,
    run_id: uuid.UUID | None = None,
    activity_id: uuid.UUID | None = None,
) -> tuple[list[Workout], PlanAdjustmentOutput, AgentExecutionLog] | None:
    """Re-modulates the workouts in (after, after + days_affected]. None if nothing to adjust."""
    plan = await active_plan(session, user.id)
    if plan is None:
        raise NoActivePlanError("No active plan")
    window_end = after + timedelta(days=request.days_affected)
    candidates = await workouts_between(session, plan.id, after + timedelta(days=1), window_end)
    if not candidates:
        return None

    today = local_today(user)
    ctx, calibration = await athlete_context(session, user, today)
    ctx["adjustment_request"] = request.model_dump(mode="json")
    ctx["workouts_to_review"] = [dump_workout(w) for w in candidates]
    available = set(ctx["athlete"]["available_days"])
    by_id = {w.id: w for w in candidates}

    def validate(out: PlanAdjustmentOutput) -> list[str]:
        v: list[str] = []
        ids = Counter(a.workout_id for a in out.adjustments)
        if set(ids) != set(by_id):
            v.append(f"return exactly one adjustment for each of: {sorted(map(str, by_id))}")
        v.extend(f"workout {i} appears {n} times" for i, n in ids.items() if n > 1)
        for a in out.adjustments:
            if a.new_workout is None:
                continue
            if not after < a.new_workout.scheduled_date <= window_end:
                v.append(f"new workout for {a.workout_id} must stay within {after} → {window_end}")
            v.extend(_draft_violations(a.new_workout, available, calibration))
        return v

    output, log = await run_agent(
        session,
        llm,
        user_id=user.id,
        agent=AgentName.TRAINING_PERIODIZATION,
        trigger=trigger,
        run_id=run_id or uuid.uuid4(),
        system=prompts.TRAINING_PERIODIZATION,
        task="Adjust the plan: review every workout in workouts_to_review "
        "according to adjustment_request.",
        context=ctx,
        output_model=PlanAdjustmentOutput,
        effort="medium",
        max_tokens=16000,
        validate=validate,
        activity_id=activity_id,
        plan_id=plan.id,
    )

    modified = [
        _apply(by_id[a.workout_id], a)
        for a in output.adjustments
        if a.action != WorkoutAdjustmentAction.KEEP
    ]
    session.add_all(modified)
    await session.commit()
    return modified, output, log


def _apply(workout: Workout, adj: WorkoutAdjustment) -> Workout:
    if workout.original_snapshot is None:  # keep the very first version across adjustments
        workout.original_snapshot = _snapshot(workout)
    draft = adj.new_workout
    if adj.action == WorkoutAdjustmentAction.REST and draft is None:
        workout.workout_type = WorkoutType.REST
        workout.title = "Riposo"
        workout.description = None
        workout.target_duration_s = workout.target_distance_m = None
        workout.structure = []
    elif draft is not None:
        workout.scheduled_date = draft.scheduled_date
        workout.session_slot = draft.session_slot
        workout.workout_type = draft.workout_type
        workout.title = draft.title
        workout.description = draft.description
        workout.target_duration_s = draft.target_duration_s
        workout.target_distance_m = draft.target_distance_m
        workout.structure = [s.model_dump(mode="json") for s in draft.structure]
    workout.status = WorkoutStatus.MODIFIED
    workout.modification_reason = adj.reason
    return workout


def _snapshot(workout: Workout) -> dict[str, Any]:
    return WorkoutDraft.model_validate(
        {
            "scheduled_date": workout.scheduled_date,
            "session_slot": workout.session_slot,
            "workout_type": workout.workout_type,
            "title": workout.title,
            "description": workout.description,
            "target_duration_s": workout.target_duration_s,
            "target_distance_m": workout.target_distance_m,
            "structure": workout.structure,
        }
    ).model_dump(mode="json")
