"""Morning check-in persistence and its deterministic summary (no LLM)."""

import uuid
from datetime import date, timedelta
from statistics import fmean

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import DailyWellness
from app.schemas.wellness import WellnessCheckIn, WellnessPeriod, WellnessSummary

RECENT_DAYS = 7
BASELINE_DAYS = 28


async def upsert_check_in(
    session: AsyncSession, user_id: uuid.UUID, day: date, check_in: WellnessCheckIn
) -> DailyWellness:
    row = (
        await session.exec(
            select(DailyWellness).where(DailyWellness.user_id == user_id, DailyWellness.day == day)
        )
    ).first() or DailyWellness(user_id=user_id, day=day)
    row.sleep_hours = check_in.sleep_hours
    row.feeling = check_in.feeling
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_wellness(
    session: AsyncSession, user_id: uuid.UUID, start: date, end: date
) -> list[DailyWellness]:
    stmt = (
        select(DailyWellness)
        .where(
            DailyWellness.user_id == user_id,
            col(DailyWellness.day) >= start,
            col(DailyWellness.day) <= end,
        )
        .order_by(col(DailyWellness.day))
    )
    return list((await session.exec(stmt)).all())


def _period(rows: list[DailyWellness]) -> WellnessPeriod:
    sleep = [r.sleep_hours for r in rows if r.sleep_hours is not None]
    feeling = [r.feeling for r in rows if r.feeling is not None]
    return WellnessPeriod(
        days_logged=sum(1 for r in rows if r.sleep_hours is not None or r.feeling is not None),
        avg_sleep_hours=round(fmean(sleep), 1) if sleep else None,
        avg_feeling=round(fmean(feeling), 1) if feeling else None,
    )


async def wellness_summary(session: AsyncSession, user_id: uuid.UUID, day: date) -> WellnessSummary:
    """Check-in of `day`, the last 7 days (day included) and the 28 days before them."""
    start = day - timedelta(days=RECENT_DAYS + BASELINE_DAYS - 1)
    rows = await list_wellness(session, user_id, start, day)
    recent_from = day - timedelta(days=RECENT_DAYS - 1)
    today = next((r for r in rows if r.day == day), None)
    return WellnessSummary(
        day=day,
        check_in=WellnessCheckIn(sleep_hours=today.sleep_hours, feeling=today.feeling)
        if today
        else None,
        last_7d=_period([r for r in rows if r.day >= recent_from]),
        previous_28d=_period([r for r in rows if r.day < recent_from]),
    )
