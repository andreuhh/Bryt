"""Deterministic workout operations shared by agents and endpoints (no LLM here)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import AgentExecutionLog, Workout, WorkoutRevision
from app.models.enums import (
    AgentName,
    RevisionSource,
    RevisionStatus,
    WorkoutDetail,
    WorkoutStatus,
)
from app.schemas.training import WorkoutDraft

CONFIRM_DAYS = 14  # rolling window of fully detailed workouts


def confirmed_until(today: date) -> date:
    return today + timedelta(days=CONFIRM_DAYS)


def detail_for(day: date, today: date) -> WorkoutDetail:
    return WorkoutDetail.CONFIRMED if day <= confirmed_until(today) else WorkoutDetail.PROVISIONAL


def strip_provisional(draft: WorkoutDraft) -> WorkoutDraft:
    """Far-ahead sessions keep type, volume and zones, never exact pace/HR (false precision)."""
    steps = [s.model_copy(update={"target_pace": None, "target_hr": None}) for s in draft.structure]
    return draft.model_copy(update={"structure": steps})


def snapshot(workout: Workout) -> dict[str, Any]:
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
            "is_key_session": workout.is_key_session,
        }
    ).model_dump(mode="json")


def new_workout(
    user_id: uuid.UUID, plan_id: uuid.UUID, draft: WorkoutDraft, today: date
) -> Workout:
    detail = detail_for(draft.scheduled_date, today)
    if detail == WorkoutDetail.PROVISIONAL:
        draft = strip_provisional(draft)
    workout = Workout(
        user_id=user_id,
        plan_id=plan_id,
        scheduled_date=draft.scheduled_date,
        workout_type=draft.workout_type,
        title=draft.title,
    )
    _copy(workout, draft)
    workout.detail_level = detail
    return workout


def _copy(workout: Workout, draft: WorkoutDraft) -> None:
    workout.scheduled_date = draft.scheduled_date
    workout.session_slot = draft.session_slot
    workout.workout_type = draft.workout_type
    workout.title = draft.title
    workout.description = draft.description
    workout.target_duration_s = draft.target_duration_s
    workout.target_distance_m = draft.target_distance_m
    workout.structure = [s.model_dump(mode="json") for s in draft.structure]
    workout.is_key_session = draft.is_key_session


def materially_changed(before: dict[str, Any], after: WorkoutDraft) -> bool:
    """Adding detail (paces) to a provisional session is not a change worth notifying."""
    keys = (
        "scheduled_date",
        "session_slot",
        "workout_type",
        "target_duration_s",
        "target_distance_m",
    )
    new = after.model_dump(mode="json")
    return any(before.get(k) != new.get(k) for k in keys)


def apply_draft(
    session: AsyncSession,
    workout: Workout,
    draft: WorkoutDraft,
    *,
    reason: str,
    source: RevisionSource,
    agent_run_id: uuid.UUID | None,
    mark_modified: bool,
    detail: WorkoutDetail | None = None,
) -> WorkoutRevision | None:
    """Updates the workout and records an APPLIED revision when something material changed."""
    before = snapshot(workout)
    if workout.original_snapshot is None and mark_modified:
        workout.original_snapshot = before  # the very first version, kept across changes
    _copy(workout, draft)
    if detail is not None:
        workout.detail_level = detail
    if mark_modified:
        workout.status = WorkoutStatus.MODIFIED
        workout.modification_reason = reason
    session.add(workout)
    if not (mark_modified or materially_changed(before, draft)):
        return None
    revision = WorkoutRevision(
        user_id=workout.user_id,
        plan_id=workout.plan_id,
        workout_id=workout.id,
        status=RevisionStatus.APPLIED,
        source=source,
        before=before,
        after=draft.model_dump(mode="json"),
        reason=reason,
        agent_run_id=agent_run_id,
        resolved_at=datetime.now(UTC),
    )
    session.add(revision)
    return revision


async def propose(
    session: AsyncSession,
    workout: Workout,
    draft: WorkoutDraft,
    *,
    reason: str,
    agent_run_id: uuid.UUID | None,
) -> WorkoutRevision:
    """PENDING proposal for a far-ahead key session; supersedes older pending ones."""
    await _supersede_pending(session, workout.id)
    revision = WorkoutRevision(
        user_id=workout.user_id,
        plan_id=workout.plan_id,
        workout_id=workout.id,
        status=RevisionStatus.PENDING,
        source=RevisionSource.WEEKLY_REFINEMENT,
        before=snapshot(workout),
        after=strip_provisional(draft).model_dump(mode="json"),
        reason=reason,
        agent_run_id=agent_run_id,
    )
    session.add(revision)
    return revision


async def _supersede_pending(
    session: AsyncSession, workout_id: uuid.UUID, keep: uuid.UUID | None = None
) -> None:
    stmt = select(WorkoutRevision).where(
        WorkoutRevision.workout_id == workout_id,
        WorkoutRevision.status == RevisionStatus.PENDING,
    )
    for rev in (await session.exec(stmt)).all():
        if rev.id != keep:
            rev.status = RevisionStatus.SUPERSEDED
            rev.resolved_at = datetime.now(UTC)
            session.add(rev)


class ProposalNotApplicableError(Exception):
    pass


async def resolve_proposal(
    session: AsyncSession, revision: WorkoutRevision, *, accept: bool, today: date
) -> Workout:
    if revision.status != RevisionStatus.PENDING:
        raise ProposalNotApplicableError(f"Proposal already {revision.status.value}")
    workout = await session.get(Workout, revision.workout_id)
    assert workout is not None  # FK with cascade
    now = datetime.now(UTC)
    if not accept:
        revision.status, revision.resolved_at = RevisionStatus.REJECTED, now
        session.add(revision)
        await session.commit()
        return workout
    if workout.status == WorkoutStatus.COMPLETED or workout.scheduled_date <= today:
        revision.status, revision.resolved_at = RevisionStatus.SUPERSEDED, now
        session.add(revision)
        await session.commit()
        raise ProposalNotApplicableError("The workout is no longer in the future")

    draft = WorkoutDraft.model_validate(revision.after)
    workout.original_snapshot = workout.original_snapshot or snapshot(workout)
    _copy(workout, draft)
    workout.detail_level = detail_for(draft.scheduled_date, today)
    workout.status = WorkoutStatus.MODIFIED
    workout.modification_reason = revision.reason
    revision.status, revision.resolved_at = RevisionStatus.APPLIED, now
    session.add_all([workout, revision])
    await _supersede_pending(session, workout.id, keep=revision.id)
    await session.commit()
    await session.refresh(workout)
    return workout


async def history(session: AsyncSession, workout_id: uuid.UUID) -> list[WorkoutRevision]:
    stmt = (
        select(WorkoutRevision)
        .where(WorkoutRevision.workout_id == workout_id)
        .order_by(col(WorkoutRevision.created_at))
    )
    return list((await session.exec(stmt)).all())


async def revert_activity_adjustments(
    session: AsyncSession, activity_id: uuid.UUID, today: date
) -> list[Workout]:
    """Undo the plan changes of previous analyses of the same activity.

    Re-analysis (e.g. after editing the context tags) must decide from the original plan,
    not stack a new reduction on top of the previous one. Past or completed workouts are
    left untouched. Reverted revisions become SUPERSEDED (history is kept).
    """
    run_ids = select(AgentExecutionLog.id).where(
        AgentExecutionLog.activity_id == activity_id,
        AgentExecutionLog.agent_name == AgentName.TRAINING_PERIODIZATION,
    )
    stmt = (
        select(WorkoutRevision)
        .where(
            col(WorkoutRevision.agent_run_id).in_(run_ids),
            WorkoutRevision.status == RevisionStatus.APPLIED,
            WorkoutRevision.source == RevisionSource.POST_ACTIVITY,
        )
        .order_by(col(WorkoutRevision.created_at))
    )
    by_workout: dict[uuid.UUID, list[WorkoutRevision]] = {}
    for rev in (await session.exec(stmt)).all():
        by_workout.setdefault(rev.workout_id, []).append(rev)

    now = datetime.now(UTC)
    reverted: list[Workout] = []
    for workout_id, revisions in by_workout.items():
        workout = await session.get(Workout, workout_id)
        if workout is None or workout.status == WorkoutStatus.COMPLETED:
            continue
        if workout.scheduled_date < today:
            continue
        first = revisions[0]
        if first.before is not None:
            _copy(workout, WorkoutDraft.model_validate(first.before))
            workout.detail_level = detail_for(workout.scheduled_date, today)
        for rev in revisions:
            rev.status, rev.resolved_at = RevisionStatus.SUPERSEDED, now
            session.add(rev)
        others = [
            r
            for r in await history(session, workout_id)
            if r.status == RevisionStatus.APPLIED and r.id not in {x.id for x in revisions}
        ]
        if others:
            workout.modification_reason = others[-1].reason
        else:
            workout.status = WorkoutStatus.PLANNED
            workout.original_snapshot = None
            workout.modification_reason = None
        session.add(workout)
        reverted.append(workout)
    await session.flush()
    return reverted
