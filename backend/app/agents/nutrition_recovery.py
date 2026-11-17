"""NutritionRecoveryAgent: bipartite output (nutrition_protocol + recovery_protocol)."""

import uuid

from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents import prompts
from app.agents.context import (
    athlete_context,
    dump_activity,
    local_today,
    plan_context,
    wellness_context,
)
from app.agents.llm import LLMClient
from app.agents.runner import run_agent
from app.models import Activity, AgentExecutionLog, User
from app.models.enums import AgentName, AgentTrigger
from app.schemas.agents import MechanicalLoadOutput, NutritionRecoveryOutput, PlanAdjustmentOutput

NEXT_DAYS = 2


async def recommend(
    session: AsyncSession,
    llm: LLMClient,
    user: User,
    activity: Activity,
    mechanical: MechanicalLoadOutput,
    adjustment: PlanAdjustmentOutput | None,
    *,
    run_id: uuid.UUID,
) -> tuple[NutritionRecoveryOutput, AgentExecutionLog]:
    today = local_today(user)
    ctx, _ = await athlete_context(session, user, today)
    plan = await plan_context(session, user.id, today, NEXT_DAYS)
    variable = {
        "activity": dump_activity(activity),
        "mechanical_load_analysis": mechanical.model_dump(mode="json"),
        "plan_adjustment": adjustment.model_dump(mode="json") if adjustment else None,
        "next_sessions": plan.get("upcoming_workouts", []),
        "wellness": await wellness_context(session, user.id, today),
    }
    return await run_agent(
        session,
        llm,
        user_id=user.id,
        agent=AgentName.NUTRITION_RECOVERY,
        trigger=AgentTrigger.POST_ACTIVITY,
        run_id=run_id,
        system=prompts.NUTRITION_RECOVERY,
        task="Produce the nutrition and recovery protocols for the next 24-48 hours.",
        context=variable,
        stable_context=ctx,
        cache_prefix=False,  # one-shot: no other call re-reads this prefix
        output_model=NutritionRecoveryOutput,
        effort="medium",
        max_tokens=16000,
        activity_id=activity.id,
    )
