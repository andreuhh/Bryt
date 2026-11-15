"""Background jobs: plan generation and the weekly refinement scheduler.

The scheduler runs inside the API process (asyncio task started in the app lifespan) and
wakes up every SCHEDULER_INTERVAL_S. Each plan is *claimed* with an atomic conditional
UPDATE before refining, so several API instances never refine the same plan twice.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import or_, update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents.llm import get_llm
from app.agents.training_periodization import build_plan, refine_plan
from app.core.config import get_settings
from app.core.database import SessionFactory
from app.models import TrainingPlan, User
from app.models.enums import PlanStatus

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
