"""Post-ingestion cascade (deterministic orchestration, no free-form agent dialogue):

    MechanicalLoadAgent ──► plan_adjustment_needed? ──► TrainingPeriodizationAgent (3-4 days)
            └──────────────────────────────────────────► NutritionRecoveryAgent

All steps share one pipeline_run_id in AgentExecutionLog.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents.context import MissingProfileError
from app.agents.llm import AgentError, LLMClient, get_llm
from app.agents.mechanical_load import analyze_activity
from app.agents.nutrition_recovery import recommend
from app.agents.training_periodization import NoActivePlanError, adjust_plan
from app.core.config import get_settings
from app.core.database import SessionFactory
from app.models import Activity, User
from app.models.enums import AgentTrigger
from app.schemas.agents import MechanicalLoadOutput, NutritionRecoveryOutput, PlanAdjustmentOutput

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    run_id: uuid.UUID
    mechanical: MechanicalLoadOutput | None = None
    adjustment: PlanAdjustmentOutput | None = None
    nutrition: NutritionRecoveryOutput | None = None
    errors: list[str] = field(default_factory=list)


async def run_post_activity_pipeline(
    session: AsyncSession, llm: LLMClient, user: User, activity: Activity
) -> PipelineResult:
    result = PipelineResult(run_id=uuid.uuid4())
    try:
        result.mechanical, _ = await analyze_activity(
            session, llm, user, activity, run_id=result.run_id
        )
    except (AgentError, MissingProfileError) as exc:
        result.errors.append(f"mechanical_load: {exc}")
        return result  # nothing downstream makes sense without the analysis

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
    return result


PipelineLauncher = Callable[[uuid.UUID, uuid.UUID], Awaitable[None]]


async def run_pipeline_in_background(user_id: uuid.UUID, activity_id: uuid.UUID) -> None:
    """BackgroundTasks entry point: own session, never raises."""
    async with SessionFactory() as session:
        user = await session.get(User, user_id)
        activity = await session.get(Activity, activity_id)
        if user is None or activity is None or activity.user_id != user_id:
            return
        result = await run_post_activity_pipeline(session, get_llm(), user, activity)
        if result.errors:
            logger.warning(
                "Pipeline %s for activity %s: %s", result.run_id, activity_id, result.errors
            )


async def _noop(user_id: uuid.UUID, activity_id: uuid.UUID) -> None:
    return None


def get_pipeline_launcher() -> PipelineLauncher:
    """FastAPI dependency: overridden in tests; disabled with AGENTS_ENABLED=false."""
    return run_pipeline_in_background if get_settings().agents_enabled else _noop
