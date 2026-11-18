"""Post-ingestion cascade (deterministic orchestration, no free-form agent dialogue):

    MechanicalLoadAgent ──► plan_adjustment_needed? ──► TrainingPeriodizationAgent (3-4 days)
            └──────────────────────────────────────────► NutritionRecoveryAgent

The deterministic triage (services/triage.py) runs the MechanicalLoadAgent FULL (its model)
or LIGHT (easy run without red flags: light model, short, never adjusts the plan). A
re-analysis requested by the athlete is always FULL.

All steps share one pipeline_run_id in AgentExecutionLog.
"""

import logging
import uuid
from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlmodel import col, func, or_, select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents.context import MissingProfileError, local_today
from app.agents.llm import AgentError, LLMClient, get_llm
from app.agents.mechanical_load import analyze_activity
from app.agents.nutrition_recovery import recommend
from app.agents.training_periodization import NoActivePlanError, adjust_plan
from app.core.config import get_settings
from app.core.database import SessionFactory
from app.models import Activity, AgentExecutionLog, User
from app.models.enums import AgentName, AgentRunStatus, AgentTrigger
from app.schemas.agents import MechanicalLoadOutput, NutritionRecoveryOutput, PlanAdjustmentOutput
from app.services.workouts import revert_activity_adjustments

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    run_id: uuid.UUID
    mechanical: MechanicalLoadOutput | None = None
    adjustment: PlanAdjustmentOutput | None = None
    nutrition: NutritionRecoveryOutput | None = None
    errors: list[str] = field(default_factory=list)


# A crashed run (process killed mid-pipeline) never releases its claim: it expires instead
ANALYSIS_STALE_AFTER = timedelta(minutes=10)


def analysis_running(activity: Activity, now: datetime | None = None) -> bool:
    started = activity.analysis_started_at
    return started is not None and (now or datetime.now(UTC)) - started < ANALYSIS_STALE_AFTER


async def claim_analysis(session: AsyncSession, activity_id: uuid.UUID) -> bool:
    """Atomic: one pipeline per activity at a time (backend poll, sync, button, other tabs).
    DB clock, like the logs' created_at that the report compares it with."""
    result = await session.exec(
        update(Activity)
        .where(
            col(Activity.id) == activity_id,
            or_(
                col(Activity.analysis_started_at).is_(None),
                col(Activity.analysis_started_at) < func.now() - ANALYSIS_STALE_AFTER,
            ),
        )
        .values(analysis_started_at=func.now())
        .execution_options(synchronize_session=False)  # loaded objects are not refreshed
    )
    await session.commit()
    return bool(result.rowcount)


async def release_analysis(session: AsyncSession, activity_id: uuid.UUID) -> None:
    await session.exec(
        update(Activity)
        .where(col(Activity.id) == activity_id)
        .values(analysis_started_at=None)
        .execution_options(synchronize_session=False)
    )
    await session.commit()


async def run_post_activity_pipeline(
    session: AsyncSession,
    llm: LLMClient,
    user: User,
    activity: Activity,
    *,
    claimed: bool = False,
) -> PipelineResult:
    """`claimed`: the caller already holds the activity's claim (athlete requests claim it before
    answering, so the report shows the run in progress right away)."""
    result = PipelineResult(run_id=uuid.uuid4())
    if not claimed and not await claim_analysis(session, activity.id):
        result.errors.append("analysis already running")
        return result
    try:
        await _run_agents(session, llm, user, activity, result)
    finally:
        try:
            await release_analysis(session, activity.id)
        except Exception:  # the claim expires on its own (ANALYSIS_STALE_AFTER)
            logger.exception("Could not release the analysis claim of activity %s", activity.id)
    return result


async def _run_agents(
    session: AsyncSession, llm: LLMClient, user: User, activity: Activity, result: PipelineResult
) -> None:
    reanalysis = await completed_analyses(session, user.id, activity.id) > 0
    try:
        result.mechanical, _ = await analyze_activity(
            session, llm, user, activity, run_id=result.run_id, reanalysis=reanalysis
        )
    except (AgentError, MissingProfileError) as exc:
        result.errors.append(f"mechanical_load: {exc}")
        return  # nothing downstream makes sense without the analysis

    # A re-analysis replaces the previous one: undo its plan changes before deciding again
    await revert_activity_adjustments(session, activity.id, local_today(user))
    await session.commit()

    request = result.mechanical.adjustment_request
    if result.mechanical.plan_adjustment_needed and request is not None:
        activity_day = activity.start_time.astimezone(ZoneInfo(user.timezone)).date()
        try:
            adjusted = await adjust_plan(
                session,
                llm,
                user,
                request=request,
                trigger=AgentTrigger.POST_ACTIVITY,
                after=activity_day,
                run_id=result.run_id,
                activity_id=activity.id,
            )
            result.adjustment = adjusted[1] if adjusted else None
        except NoActivePlanError:
            result.errors.append("plan_adjustment: no active plan")
        except AgentError as exc:  # nutrition still useful without the new plan
            result.errors.append(f"plan_adjustment: {exc}")

    try:
        result.nutrition, _ = await recommend(
            session,
            llm,
            user,
            activity,
            result.mechanical,
            result.adjustment,
            run_id=result.run_id,
        )
    except AgentError as exc:
        result.errors.append(f"nutrition_recovery: {exc}")


class PipelineLauncher(Protocol):
    def __call__(
        self, user_id: uuid.UUID, activity_id: uuid.UUID, *, claimed: bool = False
    ) -> Awaitable[None]: ...


async def completed_analyses(
    session: AsyncSession, user_id: uuid.UUID, activity_id: uuid.UUID
) -> int:
    """Successful load assessments of the activity (one per pipeline run; failures excluded)."""
    count: int = (
        await session.exec(
            select(func.count(func.distinct(AgentExecutionLog.pipeline_run_id))).where(
                AgentExecutionLog.user_id == user_id,
                AgentExecutionLog.activity_id == activity_id,
                AgentExecutionLog.trigger == AgentTrigger.POST_ACTIVITY,
                AgentExecutionLog.agent_name == AgentName.MECHANICAL_LOAD,
                AgentExecutionLog.status == AgentRunStatus.SUCCESS,
            )
        )
    ).one()
    return count


async def analyses_left(session: AsyncSession, user_id: uuid.UUID, activity_id: uuid.UUID) -> int:
    """Cost cap per activity: completed analyses against MAX_ANALYSES_PER_ACTIVITY."""
    done = await completed_analyses(session, user_id, activity_id)
    return max(get_settings().max_analyses_per_activity - done, 0)


async def run_pipeline_in_background(
    user_id: uuid.UUID, activity_id: uuid.UUID, *, claimed: bool = False
) -> None:
    """BackgroundTasks entry point: own session, never raises."""
    async with SessionFactory() as session:
        user = await session.get(User, user_id)
        activity = await session.get(Activity, activity_id)
        if user is None or activity is None or activity.user_id != user_id:
            return
        result = await run_post_activity_pipeline(
            session, get_llm(), user, activity, claimed=claimed
        )
        if result.errors:
            logger.warning(
                "Pipeline %s for activity %s: %s", result.run_id, activity_id, result.errors
            )


async def _noop(user_id: uuid.UUID, activity_id: uuid.UUID, *, claimed: bool = False) -> None:
    return None


def agents_disabled(launch: PipelineLauncher) -> bool:
    """AGENTS_ENABLED=false: the launcher does nothing, so an analysis would never arrive."""
    return launch is _noop


def get_pipeline_launcher() -> PipelineLauncher:
    """FastAPI dependency: overridden in tests; disabled with AGENTS_ENABLED=false."""
    return run_pipeline_in_background if get_settings().agents_enabled else _noop
