"""MechanicalLoadAgent: post-activity mechanical stress, divergence and context analysis."""

import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents import prompts
from app.agents.context import activity_context, athlete_context, local_today
from app.agents.llm import LLMClient
from app.agents.runner import run_agent
from app.models import Activity, AgentExecutionLog, User, Workout
from app.models.enums import AgentName, AgentTrigger
from app.schemas.agents import MechanicalLoadOutput


async def analyze_activity(
    session: AsyncSession,
    llm: LLMClient,
    user: User,
    activity: Activity,
    *,
    run_id: uuid.UUID,
) -> tuple[MechanicalLoadOutput, AgentExecutionLog]:
    ctx, _ = await athlete_context(session, user, local_today(user))
    ctx |= await activity_context(session, activity)
    planned = (
        await session.exec(select(Workout.id).where(Workout.activity_id == activity.id))
    ).first()

    def validate(out: MechanicalLoadOutput) -> list[str]:
        if out.execution.workout_id not in (None, planned):
            return [f"execution.workout_id must be {planned} or null"]
        divergence = ctx["activity"]["computed_metrics"].get("cadence_hr_divergence", {})
        codes = {a.code for a in out.alerts}
        if divergence.get("mechanical_breakdown") and "MECHANICAL_BREAKDOWN" not in codes:
            return ["deterministic analysis found a mechanical breakdown: add that alert"]
        return []

    return await run_agent(
        session,
        llm,
        user_id=user.id,
        agent=AgentName.MECHANICAL_LOAD,
        trigger=AgentTrigger.POST_ACTIVITY,
        run_id=run_id,
        system=prompts.MECHANICAL_LOAD,
        task="Analyze the activity in the context.",
        context=ctx,
        output_model=MechanicalLoadOutput,
        effort="medium",
        max_tokens=16000,
        validate=validate,
        activity_id=activity.id,
    )
