"""Single ingestion path for every .fit, whatever its origin (Intervals.icu or manual upload).

hash → dedup → parse (deterministic) → store file → Activity + ActivityStream → link the
PLANNED workout of the same local day (→ COMPLETED).
"""

import asyncio
import hashlib
import uuid
from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Activity, ActivityStream, TrainingPlan, User, Workout
from app.models.enums import (
    ActivitySource,
    PlanStatus,
    SessionSlot,
    WorkoutStatus,
    WorkoutType,
)
from app.services.fit_parser import ParsedFit, parse_fit
from app.services.storage import FitStorage


@dataclass
class IngestResult:
    activity: Activity
    created: bool


async def ingest_fit(
    session: AsyncSession,
    *,
    user: User,
    fit_bytes: bytes,
    source: ActivitySource,
    storage: FitStorage,
    external_id: str | None = None,
    name: str | None = None,
) -> IngestResult:
    """Idempotent: the same file / external activity is never ingested twice for a user.

    Raises FitParseError / UnsupportedSportError (from the parser) on invalid input.
    """
    sha256 = hashlib.sha256(fit_bytes).hexdigest()
    existing = await _find_existing(session, user.id, sha256, source, external_id)
    if existing is not None:
        return IngestResult(existing, created=False)

    # CPU-bound parsing off the event loop
    parsed = await asyncio.to_thread(parse_fit, fit_bytes)
    path = await storage.save(user.id, sha256, fit_bytes)

    activity = _build_activity(user.id, parsed, source, external_id, sha256, path, name)
    session.add(activity)
    streams = parsed.streams
    session.add(
        ActivityStream(
            user_id=user.id,
            activity_id=activity.id,
            sample_count=parsed.sample_count,
            elapsed_s=[x or 0.0 for x in streams["elapsed_s"]],
            distance_m=streams["distance_m"],
            pace_s_per_km=streams["pace_s_per_km"],
            heart_rate=streams["heart_rate"],
            cadence_spm=streams["cadence_spm"],
            elevation_m=streams["elevation_m"],
            ground_contact_ms=streams["ground_contact_ms"],
        )
    )
    workout = await _matching_planned_workout(session, user, parsed)
    if workout is not None:
        workout.status = WorkoutStatus.COMPLETED
        workout.activity_id = activity.id
        session.add(workout)

    try:
        await session.commit()
    except IntegrityError:
        # Concurrent ingestion of the same activity (e.g. webhook + manual sync)
        await session.rollback()
        existing = await _find_existing(session, user.id, sha256, source, external_id)
        if existing is None:
            raise
        return IngestResult(existing, created=False)

    await session.refresh(activity)
    # STEP 4: trigger the post-activity agent pipeline (MechanicalLoad → … → NutritionRecovery)
    return IngestResult(activity, created=True)


async def _find_existing(
    session: AsyncSession,
    user_id: uuid.UUID,
    sha256: str,
    source: ActivitySource,
    external_id: str | None,
) -> Activity | None:
    match = col(Activity.fit_sha256) == sha256
    if external_id is not None:
        match = or_(
            match, (col(Activity.source) == source) & (col(Activity.external_id) == external_id)
        )
    stmt = select(Activity).where(Activity.user_id == user_id, match)
    return (await session.exec(stmt)).first()


def _build_activity(
    user_id: uuid.UUID,
    parsed: ParsedFit,
    source: ActivitySource,
    external_id: str | None,
    sha256: str,
    path: str,
    name: str | None,
) -> Activity:
    return Activity(
        id=uuid.uuid4(),
        user_id=user_id,
        source=source,
        external_id=external_id,
        fit_sha256=sha256,
        fit_storage_path=path,
        name=name,
        sport=parsed.sport or "running",
        start_time=parsed.start_time,
        duration_s=parsed.duration_s,
        moving_time_s=parsed.moving_time_s,
        distance_m=parsed.distance_m,
        avg_pace_s_per_km=parsed.avg_pace_s_per_km,
        avg_hr=parsed.avg_hr,
        max_hr=parsed.max_hr,
        avg_cadence_spm=parsed.avg_cadence_spm,
        avg_ground_contact_ms=parsed.avg_ground_contact_ms,
        elevation_gain_m=parsed.elevation_gain_m,
        elevation_loss_m=parsed.elevation_loss_m,
        computed_metrics=parsed.computed.model_dump(mode="json"),
        surface=parsed.surface,
        context_tags={},
    )


async def _matching_planned_workout(
    session: AsyncSession, user: User, parsed: ParsedFit
) -> Workout | None:
    local_start = parsed.start_time.astimezone(ZoneInfo(user.timezone))
    day: date = local_start.date()
    stmt = (
        select(Workout)
        .join(TrainingPlan, col(TrainingPlan.id) == col(Workout.plan_id))
        .where(TrainingPlan.status == PlanStatus.ACTIVE)
        .where(
            Workout.user_id == user.id,
            Workout.scheduled_date == day,
            Workout.status == WorkoutStatus.PLANNED,
            col(Workout.activity_id).is_(None),
            Workout.workout_type != WorkoutType.REST,
        )
    )
    candidates = list((await session.exec(stmt)).all())
    if not candidates:
        return None
    # Double threshold days: AM/PM sessions matched by the hour of the run
    preferred = SessionSlot.AM if local_start.hour < 14 else SessionSlot.PM
    candidates.sort(
        key=lambda w: (w.session_slot != preferred, w.session_slot != SessionSlot.SINGLE)
    )
    return candidates[0]
