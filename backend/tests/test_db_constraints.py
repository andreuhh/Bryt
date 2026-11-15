"""Integration tests against the real PostgreSQL schema (alembic upgrade head).

Every test runs inside a transaction that is rolled back. Skipped if the DB is unreachable.
"""

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    Activity,
    PersonalBest,
    TrainingPlan,
    User,
    UserLifestyleProfile,
    Workout,
)
from app.models.enums import (
    ActivitySource,
    AthleteBackground,
    Methodology,
    TrainingSlot,
    Weekday,
    WorkoutType,
    WorkType,
)


async def _user(session: AsyncSession) -> User:
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4().hex[:8]}@bryt.test")
    session.add(user)
    await session.flush()
    return user


def _activity(user_id: uuid.UUID, external_id: str) -> Activity:
    return Activity(
        user_id=user_id,
        source=ActivitySource.INTERVALS,
        external_id=external_id,
        start_time=datetime(2026, 11, 1, 7, 0, tzinfo=UTC),
        duration_s=3600,
        distance_m=12000,
    )


async def test_full_graph_roundtrip(session: AsyncSession) -> None:
    user = await _user(session)
    session.add(
        UserLifestyleProfile(
            user_id=user.id,
            background=AthleteBackground.ROAD,
            preferred_slot=TrainingSlot.LUNCH,
            work_type=WorkType.SEDENTARY,
            available_days=[Weekday.TUE, Weekday.SAT],
        )
    )
    session.add(
        PersonalBest(user_id=user.id, distance_m=42195, time_s=11100, achieved_on=date(2026, 4, 12))
    )
    plan = TrainingPlan(
        user_id=user.id,
        name="Maratona sub 2h55",
        methodology=Methodology.DOUBLE_THRESHOLD,
        start_date=date(2026, 11, 16),
        end_date=date(2027, 3, 21),
    )
    session.add(plan)
    await session.flush()
    session.add(
        Workout(
            user_id=user.id,
            plan_id=plan.id,
            scheduled_date=date(2026, 11, 17),
            workout_type=WorkoutType.THRESHOLD,
            title="5x6' soglia",
        )
    )
    await session.flush()

    profile = (
        await session.exec(
            select(UserLifestyleProfile).where(UserLifestyleProfile.user_id == user.id)
        )
    ).one()
    assert profile.available_days == ["TUE", "SAT"]
    assert profile.created_at is not None


async def test_one_profile_per_user(session: AsyncSession) -> None:
    user = await _user(session)
    for _ in range(2):
        session.add(
            UserLifestyleProfile(
                user_id=user.id,
                background=AthleteBackground.TRACK,
                preferred_slot=TrainingSlot.EVENING,
                work_type=WorkType.PHYSICAL,
            )
        )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_activity_external_id_dedup_per_user(session: AsyncSession) -> None:
    user_a, user_b = await _user(session), await _user(session)
    session.add_all([_activity(user_a.id, "i999"), _activity(user_b.id, "i999")])
    await session.flush()  # same external id on different tenants is fine

    session.add(_activity(user_a.id, "i999"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_deleting_user_cascades(session: AsyncSession) -> None:
    user = await _user(session)
    session.add(_activity(user.id, "i1"))
    await session.flush()

    await session.delete(user)
    await session.flush()
    remaining = (await session.exec(select(Activity).where(Activity.user_id == user.id))).all()
    assert remaining == []
