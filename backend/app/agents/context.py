"""Builds the <context> each agent receives — read-only views of the shared state."""

import uuid
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    Activity,
    ActivityStream,
    PersonalBest,
    TrainingPlan,
    User,
    Workout,
)
from app.models.enums import PlanStatus, WorkoutStatus
from app.schemas.activity import ActivityRead
from app.schemas.training import AthleteCalibration, TrainingPlanRead, WorkoutRead
from app.schemas.user import PersonalBestRead, ProfileRead
from app.services.calibration import compute_calibration
from app.services.history import elevation_quality, training_baseline
from app.services.profile import get_profile

_PRIVATE_PROFILE_FIELDS = {
    "id",
    "user_id",
    "intervals_athlete_id",
    "intervals_connected",
    "updated_at",
}
_PRIVATE_ACTIVITY_FIELDS = {"external_id"}


class MissingProfileError(Exception):
    pass


def dump_workout(workout: Workout) -> dict[str, Any]:
    return WorkoutRead.model_validate(workout).model_dump(mode="json", exclude={"plan_id"})


def dump_activity(activity: Activity) -> dict[str, Any]:
    return ActivityRead.model_validate(activity).model_dump(
        mode="json", exclude=_PRIVATE_ACTIVITY_FIELDS
    )


async def athlete_context(
    session: AsyncSession, user: User, today: date
) -> tuple[dict[str, Any], AthleteCalibration]:
    profile = await get_profile(session, user)
    if profile is None:
        raise MissingProfileError("Onboarding not completed")
    pbs = list(
        (
            await session.exec(
                select(PersonalBest)
                .where(PersonalBest.user_id == user.id)
                .order_by(col(PersonalBest.achieved_on).desc())
            )
        ).all()
    )
    calibration = compute_calibration(profile, pbs, today)
    athlete = ProfileRead.model_validate(profile).model_dump(
        mode="json", exclude=_PRIVATE_PROFILE_FIELDS
    )
    if profile.birth_year:
        athlete["age"] = today.year - profile.birth_year
    athlete["timezone"] = user.timezone
    return (
        {
            "today": today.isoformat(),
            "athlete": athlete,
            "personal_bests": [
                PersonalBestRead.model_validate(pb).model_dump(mode="json", exclude={"id"})
                for pb in pbs
            ],
            "calibration": calibration.model_dump(mode="json"),
        },
        calibration,
    )


async def active_plan(session: AsyncSession, user_id: uuid.UUID) -> TrainingPlan | None:
    stmt = select(TrainingPlan).where(
        TrainingPlan.user_id == user_id, TrainingPlan.status == PlanStatus.ACTIVE
    )
    return (await session.exec(stmt)).first()


async def workouts_between(
    session: AsyncSession,
    plan_id: uuid.UUID,
    start: date,
    end: date,
    statuses: tuple[WorkoutStatus, ...] = (WorkoutStatus.PLANNED, WorkoutStatus.MODIFIED),
) -> list[Workout]:
    stmt = (
        select(Workout)
        .where(
            Workout.plan_id == plan_id,
            col(Workout.scheduled_date) >= start,
            col(Workout.scheduled_date) <= end,
            col(Workout.status).in_(statuses),
        )
        .order_by(col(Workout.scheduled_date), col(Workout.session_slot))
    )
    return list((await session.exec(stmt)).all())


async def plan_context(
    session: AsyncSession, user_id: uuid.UUID, today: date, days: int
) -> dict[str, Any]:
    plan = await active_plan(session, user_id)
    if plan is None:
        return {"active_plan": None}
    upcoming = await workouts_between(session, plan.id, today, today + timedelta(days=days))
    return {
        "active_plan": TrainingPlanRead.model_validate(plan).model_dump(mode="json"),
        "upcoming_workouts": [dump_workout(w) for w in upcoming],
    }


async def activity_context(session: AsyncSession, activity: Activity) -> dict[str, Any]:
    planned = (
        await session.exec(select(Workout).where(Workout.activity_id == activity.id))
    ).first()
    stream = (
        await session.exec(select(ActivityStream).where(ActivityStream.activity_id == activity.id))
    ).first()
    baseline = await training_baseline(
        session, activity.user_id, activity.start_time, exclude_activity_id=activity.id
    )
    return {
        "activity": dump_activity(activity),
        "planned_workout": dump_workout(planned) if planned else None,
        "elevation_quality": elevation_quality(activity, stream).model_dump(mode="json"),
        "baseline_28d": baseline.model_dump(mode="json"),
    }


def local_today(user: User, now: datetime | None = None) -> date:
    tz = ZoneInfo(user.timezone)
    return (now or datetime.now(tz)).astimezone(tz).date()
