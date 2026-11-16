"""Background jobs: plan generation, the weekly refinement scheduler, the Intervals.icu poll.

The scheduler runs inside the API process (asyncio task started in the app lifespan) and
wakes up every SCHEDULER_INTERVAL_S. Each plan is *claimed* with an atomic conditional
UPDATE before refining, so several API instances never refine the same plan twice.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents.context import local_today
from app.agents.llm import get_llm
from app.agents.pipeline import PipelineLauncher, get_pipeline_launcher
from app.agents.training_periodization import build_plan, refine_plan
from app.core.config import get_settings
from app.core.database import SessionFactory
from app.models import TrainingPlan, User, UserLifestyleProfile
from app.models.enums import PlanStatus
from app.schemas.ingestion import SyncItemStatus
from app.services.intervals_sync import IntervalsAuthError, IntervalsError, sync_user
from app.services.storage import get_fit_storage

logger = logging.getLogger(__name__)

REFINEMENT_WEEKDAY = 6  # Sunday
REFINEMENT_HOUR = 20  # local time
MAX_DAYS_WITHOUT_REFINEMENT = 7  # catch-up if the server was down on Sunday evening


def refinement_due(last_refined_on: date | None, local_now: datetime) -> bool:
    today = local_now.date()
    if last_refined_on is None:
        return True
    if last_refined_on >= today:
        return False
    sunday_evening = local_now.weekday() == REFINEMENT_WEEKDAY and local_now.hour >= REFINEMENT_HOUR
    return sunday_evening or (today - last_refined_on).days >= MAX_DAYS_WITHOUT_REFINEMENT


async def claim_refinement(session: AsyncSession, plan_id: uuid.UUID, today: date) -> bool:
    """Atomic: only one caller can move last_refined_on to today."""
    result = await session.exec(
        update(TrainingPlan)
        .where(
            col(TrainingPlan.id) == plan_id,
            or_(
                col(TrainingPlan.last_refined_on).is_(None),
                col(TrainingPlan.last_refined_on) < today,
            ),
        )
        .values(last_refined_on=today)
    )
    await session.commit()
    return bool(result.rowcount)


async def run_due_refinements(now: datetime | None = None) -> int:
    """One scheduler tick. Returns the number of plans refined."""
    refined = 0
    async with SessionFactory() as session:
        rows = [
            (plan.id, plan.last_refined_on, user.id, user.timezone)
            for plan, user in (
                await session.exec(
                    select(TrainingPlan, User)
                    .join(User, col(User.id) == col(TrainingPlan.user_id))
                    .where(TrainingPlan.status == PlanStatus.ACTIVE)
                )
            ).all()
        ]
    for plan_id, last, user_id, tz in rows:
        local_now = (now or datetime.now(ZoneInfo(tz))).astimezone(ZoneInfo(tz))
        if not refinement_due(last, local_now):
            continue
        async with SessionFactory() as session:
            if not await claim_refinement(session, plan_id, local_now.date()):
                continue
            user = await session.get(User, user_id)
            assert user is not None
            try:
                await refine_plan(session, get_llm(), user)
                refined += 1
            except Exception:
                logger.exception("Weekly refinement failed for plan %s", plan_id)
    return refined


async def scheduler_loop() -> None:
    interval = get_settings().scheduler_interval_s
    while True:
        try:
            count = await run_due_refinements()
            if count:
                logger.info("Weekly refinement: %d plan(s) updated", count)
        except Exception:
            logger.exception("Scheduler tick failed")
        await asyncio.sleep(interval)


# --- Intervals.icu poll ---------------------------------------------------------------------

POLL_WINDOW_DAYS = 2  # yesterday's late runs + today's (AM and PM of a double threshold)


async def claim_intervals_poll(
    session: AsyncSession, profile_id: uuid.UUID, now: datetime, min_age: timedelta
) -> bool:
    """Atomic: skips athletes synced recently (by the app, the button or another instance)."""
    result = await session.exec(
        update(UserLifestyleProfile)
        .where(
            col(UserLifestyleProfile.id) == profile_id,
            or_(
                col(UserLifestyleProfile.intervals_synced_at).is_(None),
                col(UserLifestyleProfile.intervals_synced_at) < now - min_age,
            ),
        )
        .values(intervals_synced_at=now)
    )
    await session.commit()
    return bool(result.rowcount)


async def run_intervals_poll(
    now: datetime | None = None,
    launch: PipelineLauncher | None = None,
    session_factory: Callable[[], AsyncSession] = SessionFactory,
) -> int:
    """One poll tick: imports new runs of every connected athlete and analyzes them right
    away (post-run nutrition is useful now, not tonight). Returns the runs imported."""
    now = now or datetime.now(UTC)
    launch = launch or get_pipeline_launcher()  # no-op with AGENTS_ENABLED=false (no cost)
    min_age = timedelta(seconds=get_settings().intervals_poll_interval_s) - timedelta(minutes=1)
    async with session_factory() as session:
        profile_ids = list(
            (
                await session.exec(
                    select(UserLifestyleProfile.id).where(
                        col(UserLifestyleProfile.intervals_athlete_id).is_not(None),
                        col(UserLifestyleProfile.intervals_api_key_encrypted).is_not(None),
                    )
                )
            ).all()
        )
    imported = 0
    for profile_id in profile_ids:
        async with session_factory() as session:
            if not await claim_intervals_poll(session, profile_id, now, min_age):
                continue
            profile = await session.get(UserLifestyleProfile, profile_id)
            user = await session.get(User, profile.user_id) if profile else None
            if profile is None or user is None:
                continue
            today = local_today(user)
            try:
                result = await sync_user(
                    session,
                    user=user,
                    profile=profile,
                    storage=get_fit_storage(),
                    oldest=today - timedelta(days=POLL_WINDOW_DAYS),
                    newest=today,
                )
            except IntervalsAuthError:
                logger.warning("Intervals.icu poll: credentials rejected for user %s", user.id)
                continue
            except IntervalsError:
                logger.exception("Intervals.icu poll failed for user %s", user.id)
                continue
            for item in result.items:
                if item.status == SyncItemStatus.IMPORTED and item.activity_id:
                    imported += 1
                    await launch(user.id, item.activity_id)
    return imported


async def intervals_poll_loop() -> None:
    interval = get_settings().intervals_poll_interval_s
    while True:
        try:
            count = await run_intervals_poll()
            if count:
                logger.info("Intervals.icu poll: %d new run(s) imported", count)
        except Exception:
            logger.exception("Intervals.icu poll tick failed")
        await asyncio.sleep(interval)


# --- Plan generation job ------------------------------------------------------------------

PlanJobLauncher = Callable[[uuid.UUID, uuid.UUID], Awaitable[None]]


async def build_plan_in_background(user_id: uuid.UUID, plan_id: uuid.UUID) -> None:
    async with SessionFactory() as session:
        user = await session.get(User, user_id)
        plan = await session.get(TrainingPlan, plan_id)
        if user is None or plan is None or plan.user_id != user_id:
            return
        try:
            await build_plan(session, get_llm(), user, plan)
        except Exception:
            logger.exception("Plan generation failed for plan %s", plan_id)


def get_plan_job_launcher() -> PlanJobLauncher:
    """FastAPI dependency (overridden in tests)."""
    return build_plan_in_background
