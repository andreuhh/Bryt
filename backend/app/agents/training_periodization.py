"""TrainingPeriodizationAgent.

- Plan generation (background job): phase 1 skeleton (blocks/weeks to race day), phase 2
  every day of each block. Workouts within CONFIRM_DAYS are CONFIRMED (full pace/HR detail),
  the rest PROVISIONAL (zones only) — decided by code from the date, not by the model.
- Weekly refinement: provisional → confirmed for the next 2 weeks; far-ahead key sessions
  only get PENDING proposals the athlete accepts or rejects.
- Adaptive re-modulation (post-activity / chat): next 1-4 days, recorded as revisions.
"""

import uuid
from collections import Counter
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents import prompts
from app.agents.context import (
    MissingProfileError,
    active_plan,
    athlete_context,
    dump_workout,
    local_today,
    workouts_between,
)
from app.agents.llm import LLMClient
from app.agents.runner import run_agent
from app.models import AgentExecutionLog, TrainingPlan, User, Workout, WorkoutRevision
from app.models.enums import (
    AgentName,
    AgentRunStatus,
    AgentTrigger,
    PlanStatus,
    RevisionSource,
    WorkoutDetail,
    WorkoutStatus,
    WorkoutType,
)
from app.schemas.agents import (
    BlockWorkoutsOutput,
    PlanAdjustmentOutput,
    PlanAdjustmentRequest,
    PlanSkeletonOutput,
    RefinementOutput,
    WorkoutAdjustmentAction,
)
from app.schemas.training import AthleteCalibration, PlanBlock, WorkoutDraft
from app.services.history import training_baseline
from app.services.profile import get_profile
from app.services.workouts import (
    apply_draft,
    confirmed_until,
    detail_for,
    new_workout,
    propose,
    snapshot,
)

WEEKDAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
NOT_A_RUN = {WorkoutType.REST, WorkoutType.STRENGTH}
MAX_KEY_SESSIONS_PER_WEEK = 2
DEFAULT_HORIZON_WEEKS = 12
KEY_SESSION_LOOKAHEAD_DAYS = 42  # far-ahead key sessions shown to the weekly refinement
RECENT_ANALYSES_DAYS = 14


class NoActivePlanError(Exception):
    pass


# --- Shared validation --------------------------------------------------------------------


def _draft_violations(
    w: WorkoutDraft, available: set[str], calibration: AthleteCalibration
) -> list[str]:
    v: list[str] = []
    weekday = WEEKDAYS[w.scheduled_date.weekday()]
    if w.workout_type not in NOT_A_RUN and weekday not in available:
        v.append(f"'{w.title}' on {w.scheduled_date} ({weekday}): not an available day")
    zones = {z.code for z in calibration.zones}
    for step in w.structure:
        if step.target_zone and step.target_zone not in zones:
            v.append(f"'{w.title}': unknown zone '{step.target_zone}' (use {sorted(zones)})")
    return v


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


# --- Plan generation ----------------------------------------------------------------------


async def start_plan_generation(
    session: AsyncSession, user: User, *, start_date: date | None = None
) -> TrainingPlan:
    """Fast, synchronous part: validates prerequisites and creates the GENERATING plan."""
    profile = await get_profile(session, user)
    if profile is None:
        raise MissingProfileError("Onboarding not completed")
    today = local_today(user)
    start = start_date or today + timedelta(days=1)
    race = profile.target_race_date
    end = race if race and race > start else start + timedelta(weeks=DEFAULT_HORIZON_WEEKS, days=-1)
    plan = TrainingPlan(
        user_id=user.id,
        name="Piano in generazione",
        status=PlanStatus.GENERATING,
        methodology=profile.methodology,
        start_date=start,
        end_date=end,
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return plan


async def build_plan(
    session: AsyncSession, llm: LLMClient, user: User, plan: TrainingPlan
) -> TrainingPlan:
    """Slow part (background): skeleton + one call per block. Never leaves a half plan:
    on failure the plan is FAILED, its workouts removed and the previous plan kept active."""
    run_id, plan_id = uuid.uuid4(), plan.id
    try:
        await _build(session, llm, user, plan, run_id)
    except Exception as exc:
        # rollback expires loaded objects: reload by id instead of touching `plan`
        await session.rollback()
        for w in (await session.exec(select(Workout).where(Workout.plan_id == plan_id))).all():
            await session.delete(w)
        failed = await session.get(TrainingPlan, plan_id)
        assert failed is not None
        failed.status = PlanStatus.FAILED
        failed.generation_error = f"{type(exc).__name__}: {exc}"[:1000]
        session.add(failed)
        await session.commit()
        raise
    return plan


async def _build(
    session: AsyncSession, llm: LLMClient, user: User, plan: TrainingPlan, run_id: uuid.UUID
) -> None:
    today = local_today(user)
    start, end = plan.start_date, plan.end_date
    ctx, calibration = await athlete_context(session, user, today)
    ctx["baseline_28d"] = (
        await training_baseline(
            session,
            user.id,
            _midnight(today),
            declared_weekly_km=ctx["athlete"]["weekly_volume_km"],
        )
    ).model_dump(mode="json")
    available = set(ctx["athlete"]["available_days"])

    skeleton, _ = await run_agent(
        session,
        llm,
        user_id=user.id,
        agent=AgentName.TRAINING_PERIODIZATION,
        trigger=AgentTrigger.ONBOARDING,
        run_id=run_id,
        system=prompts.TRAINING_PERIODIZATION,
        task=(
            f"Phase 1 — skeleton. start_date={start}, end_date={end} (race day or end of "
            "block). Blocks must be contiguous and cover the whole range; every week needs a "
            "target_volume_km."
        ),
        context={},
        stable_context=ctx,
        output_model=PlanSkeletonOutput,
        effort="high",
        max_tokens=32000,
        validate=lambda out: _skeleton_violations(out, start, end),
        plan_id=plan.id,
    )
    plan.name = skeleton.plan_name
    plan.methodology = skeleton.methodology
    plan.goal_summary = skeleton.goal_summary[:500]
    plan.blocks = [b.model_dump(mode="json") for b in skeleton.blocks]
    plan.rationale = skeleton.rationale
    session.add(plan)

    confirm_end = confirmed_until(today)
    previous: list[dict[str, Any]] = []
    for block in sorted(skeleton.blocks, key=lambda b: b.start_date):
        # Stable across the 5-7 block calls (cached once); only the block itself varies
        block_stable = ctx | {"skeleton": skeleton.model_dump(mode="json")}
        block_ctx = {
            "current_block": block.model_dump(mode="json"),
            "previous_block_last_week": previous,
        }
        out, _ = await run_agent(
            session,
            llm,
            user_id=user.id,
            agent=AgentName.TRAINING_PERIODIZATION,
            trigger=AgentTrigger.ONBOARDING,
            run_id=run_id,
            system=prompts.TRAINING_PERIODIZATION,
            task=(
                f"Phase 2 — workouts of block '{block.name}': every day from "
                f"{block.start_date} to {block.end_date}. Full detail (pace/HR) only up to "
                f"{confirm_end}; later workouts provisional (zones only)."
            ),
            context=block_ctx,
            stable_context=block_stable,
            output_model=BlockWorkoutsOutput,
            effort="medium",
            max_tokens=64000,
            validate=_block_validator(
                block, available, calibration, ctx["athlete"]["double_sessions_ok"]
            ),
            plan_id=plan.id,
        )
        session.add_all(new_workout(user.id, plan.id, d, today) for d in out.workouts)
        last_week = block.end_date - timedelta(days=6)
        previous = [
            d.model_dump(mode="json") for d in out.workouts if d.scheduled_date >= last_week
        ]

    for old in (
        await session.exec(
            select(TrainingPlan).where(
                TrainingPlan.user_id == user.id,
                TrainingPlan.status == PlanStatus.ACTIVE,
                TrainingPlan.id != plan.id,
            )
        )
    ).all():
        old.status = PlanStatus.ARCHIVED
        session.add(old)
    plan.status = PlanStatus.ACTIVE
    plan.last_refined_on = today  # first two weeks are already confirmed
    plan.generation_error = None
    session.add(plan)
    await session.commit()


def _skeleton_violations(out: PlanSkeletonOutput, start: date, end: date) -> list[str]:
    v: list[str] = []
    if out.start_date != start or out.end_date != end:
        v.append(f"plan must span exactly {start} → {end}")
    blocks = sorted(out.blocks, key=lambda b: b.start_date)
    if blocks[0].start_date != start or blocks[-1].end_date != end:
        v.append(f"blocks must start on {start} and end on {end}")
    for prev, nxt in zip(blocks, blocks[1:], strict=False):
        if nxt.start_date != prev.end_date + timedelta(days=1):
            v.append(f"gap or overlap between '{prev.name}' and '{nxt.name}'")
    v.extend(
        f"block '{b.name}' week {w.week_index}: missing target_volume_km"
        for b in blocks
        for w in b.weeks
        if w.target_volume_km is None
    )
    return v


def _block_validator(
    block: PlanBlock, available: set[str], calibration: AthleteCalibration, double_ok: bool
) -> Callable[[BlockWorkoutsOutput], list[str]]:
    return lambda out: _block_violations(out, block, available, calibration, double_ok)


def _block_violations(
    out: BlockWorkoutsOutput,
    block: PlanBlock,
    available: set[str],
    calibration: AthleteCalibration,
    double_ok: bool,
) -> list[str]:
    v: list[str] = []
    dates = [w.scheduled_date for w in out.workouts]
    outside = sorted({d for d in dates if not block.start_date <= d <= block.end_date})
    if outside:
        v.append(f"dates outside {block.start_date} → {block.end_date}: {outside}")
    missing = [d for d in _days(block.start_date, block.end_date) if d not in set(dates)]
    if missing:
        v.append(f"missing days (add a workout or an explicit REST): {missing}")
    runs = Counter(w.scheduled_date for w in out.workouts if w.workout_type not in NOT_A_RUN)
    max_runs = 2 if double_ok else 1
    v.extend(f"{d}: more than {max_runs} run(s) in a day" for d, n in runs.items() if n > max_runs)
    keys = Counter(w.scheduled_date.isocalendar()[:2] for w in out.workouts if w.is_key_session)
    v.extend(
        f"ISO week {y}-W{wk}: {n} key sessions (max {MAX_KEY_SESSIONS_PER_WEEK}: long run, "
        "race-pace, test or race only)"
        for (y, wk), n in keys.items()
        if n > MAX_KEY_SESSIONS_PER_WEEK
    )
    for w in out.workouts:
        v.extend(_draft_violations(w, available, calibration))
    return v


# --- Weekly refinement --------------------------------------------------------------------


async def refine_plan(
    session: AsyncSession, llm: LLMClient, user: User
) -> tuple[list[Workout], list[WorkoutRevision], RefinementOutput | None]:
    """Confirms the next 2 weeks. No LLM call when nothing is provisional in the window."""
    plan = await active_plan(session, user.id)
    if plan is None:
        raise NoActivePlanError("No active plan")
    today = local_today(user)
    window_start, window_end = today + timedelta(days=1), confirmed_until(today)
    in_window = await workouts_between(
        session, plan.id, window_start, window_end, statuses=(WorkoutStatus.PLANNED,)
    )
    to_confirm = [w for w in in_window if w.detail_level == WorkoutDetail.PROVISIONAL]
    if not to_confirm:
        plan.last_refined_on = today
        session.add(plan)
        await session.commit()
        return [], [], None

    upcoming_keys = [
        w
        for w in await workouts_between(
            session,
            plan.id,
            window_end + timedelta(days=1),
            window_end + timedelta(days=KEY_SESSION_LOOKAHEAD_DAYS),
        )
        if w.is_key_session
    ]
    ctx, calibration = await athlete_context(session, user, today)
    variable = {
        "baseline_28d": (
            await training_baseline(
                session,
                user.id,
                _midnight(today + timedelta(days=1)),
                declared_weekly_km=ctx["athlete"]["weekly_volume_km"],
            )
        ).model_dump(mode="json"),
        "recent_analyses": await _recent_analyses(session, user.id, today),
        "plan_blocks": plan.blocks,
        "already_confirmed": [dump_workout(w) for w in in_window if w not in to_confirm],
        "workouts_to_confirm": [dump_workout(w) for w in to_confirm],
        "upcoming_key_sessions": [dump_workout(w) for w in upcoming_keys],
    }
    available = set(ctx["athlete"]["available_days"])
    confirm_ids = {w.id for w in to_confirm}
    key_ids = {w.id for w in upcoming_keys}

    def validate(out: RefinementOutput) -> list[str]:
        v: list[str] = []
        ids = Counter(c.workout_id for c in out.confirmed)
        if set(ids) != confirm_ids:
            v.append(f"confirm exactly these workouts: {sorted(map(str, confirm_ids))}")
        v.extend(f"workout {i} confirmed {n} times" for i, n in ids.items() if n > 1)
        for c in out.confirmed:
            if not window_start <= c.workout.scheduled_date <= window_end:
                v.append(f"{c.workout_id}: keep it within {window_start} → {window_end}")
            v.extend(_draft_violations(c.workout, available, calibration))
        for p in out.key_session_proposals:
            if p.workout_id not in key_ids:
                v.append(f"proposal for {p.workout_id}: only upcoming_key_sessions can be proposed")
            if not window_end < p.proposed.scheduled_date <= plan.end_date:
                v.append(f"proposal for {p.workout_id}: date must stay after {window_end}")
            v.extend(_draft_violations(p.proposed, available, calibration))
        return v

    output, log = await run_agent(
        session,
        llm,
        user_id=user.id,
        agent=AgentName.TRAINING_PERIODIZATION,
        trigger=AgentTrigger.WEEKLY_REFINEMENT,
        run_id=uuid.uuid4(),
        system=prompts.TRAINING_PERIODIZATION,
        task=(
            f"Weekly refinement on {today}: confirm every workout in workouts_to_confirm "
            f"({window_start} → {window_end}) with full detail. Propose changes to "
            "upcoming_key_sessions only if clearly needed."
        ),
        context=variable,
        stable_context=ctx,
        output_model=RefinementOutput,
        effort="high",
        max_tokens=32000,
        validate=validate,
        plan_id=plan.id,
    )

    by_id = {w.id: w for w in to_confirm} | {w.id: w for w in upcoming_keys}
    for c in output.confirmed:
        apply_draft(
            session,
            by_id[c.workout_id],
            c.workout,
            reason=output.notes,
            source=RevisionSource.WEEKLY_REFINEMENT,
            agent_run_id=log.id,
            mark_modified=False,
            detail=WorkoutDetail.CONFIRMED,
        )
    proposals = [
        await propose(
            session, by_id[p.workout_id], p.proposed, reason=p.reason, agent_run_id=log.id
        )
        for p in output.key_session_proposals
    ]
    plan.last_refined_on = today
    session.add(plan)
    await session.commit()
    return [by_id[c.workout_id] for c in output.confirmed], proposals, output


async def _recent_analyses(
    session: AsyncSession, user_id: uuid.UUID, today: date
) -> list[dict[str, Any]]:
    stmt = (
        select(AgentExecutionLog)
        .where(
            AgentExecutionLog.user_id == user_id,
            AgentExecutionLog.agent_name == AgentName.MECHANICAL_LOAD,
            AgentExecutionLog.status == AgentRunStatus.SUCCESS,
            col(AgentExecutionLog.created_at)
            >= _midnight(today - timedelta(days=RECENT_ANALYSES_DAYS)),
        )
        .order_by(col(AgentExecutionLog.created_at))
    )
    return [
        {
            "activity_id": str(log.activity_id),
            "summary": (log.output or {}).get("summary"),
            "alerts": (log.output or {}).get("alerts", []),
            "plan_adjustment_needed": (log.output or {}).get("plan_adjustment_needed"),
        }
        for log in (await session.exec(stmt)).all()
    ]


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
    variable = {
        "adjustment_request": request.model_dump(mode="json"),
        "workouts_to_review": [dump_workout(w) for w in candidates],
    }
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
        context=variable,
        stable_context=ctx,
        output_model=PlanAdjustmentOutput,
        effort="medium",
        max_tokens=16000,
        validate=validate,
        activity_id=activity_id,
        plan_id=plan.id,
    )

    source = (
        RevisionSource.COACH_CHAT if trigger == AgentTrigger.CHAT else RevisionSource.POST_ACTIVITY
    )
    modified: list[Workout] = []
    for adj in output.adjustments:
        if adj.action == WorkoutAdjustmentAction.KEEP:
            continue
        workout = by_id[adj.workout_id]
        draft = adj.new_workout or _rest_draft(workout)
        apply_draft(
            session,
            workout,
            draft,
            reason=adj.reason,
            source=source,
            agent_run_id=log.id,
            mark_modified=True,
            detail=detail_for(draft.scheduled_date, today),
        )
        modified.append(workout)
    await session.commit()
    return modified, output, log


def _rest_draft(workout: Workout) -> WorkoutDraft:
    return WorkoutDraft.model_validate(
        snapshot(workout)
        | {
            "workout_type": WorkoutType.REST,
            "title": "Riposo",
            "description": None,
            "target_duration_s": None,
            "target_distance_m": None,
            "structure": [],
            "is_key_session": False,
        }
    )
