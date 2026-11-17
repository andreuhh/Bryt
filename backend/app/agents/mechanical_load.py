"""MechanicalLoadAgent: post-activity mechanical stress, divergence and context analysis.

The deterministic triage (services/triage.py) picks the depth: FULL on the agent's model, or
LIGHT (easy run, no red flags) on the light model, short and without plan changes."""

import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents import prompts
from app.agents.context import activity_context, athlete_context, local_today
from app.agents.llm import LLMClient
from app.agents.runner import run_agent
from app.core.config import get_settings
from app.models import Activity, AgentExecutionLog, User, Workout
from app.models.enums import AgentName, AgentTrigger, AnalysisDepth
from app.schemas.agents import MechanicalLoadOutput
from app.services.triage import triage_activity

LIGHT_TASK = (
    "The deterministic triage classified this as an easy run with no red flags "
    "(context.triage). Keep the analysis short: a one or two sentence summary, alerts only "
    "for something the athlete must know, no plan adjustment."
)


async def analyze_activity(
    session: AsyncSession,
    llm: LLMClient,
    user: User,
    activity: Activity,
    *,
    run_id: uuid.UUID,
    reanalysis: bool = False,
) -> tuple[MechanicalLoadOutput, AgentExecutionLog]:
    ctx, calibration = await athlete_context(session, user, local_today(user))
    variable = await activity_context(session, activity)
    triage = await triage_activity(session, user, activity, calibration, reanalysis=reanalysis)
    variable["triage"] = triage.model_dump(mode="json")
    light = triage.depth == AnalysisDepth.LIGHT
    planned = (
        await session.exec(select(Workout.id).where(Workout.activity_id == activity.id))
    ).first()

    def validate(out: MechanicalLoadOutput) -> list[str]:
        if out.execution.workout_id not in (None, planned):
            return [f"execution.workout_id must be {planned} or null"]
        divergence = variable["activity"]["computed_metrics"].get("cadence_hr_divergence", {})
        codes = {a.code for a in out.alerts}
        if divergence.get("mechanical_breakdown") and "MECHANICAL_BREAKDOWN" not in codes:
            return ["deterministic analysis found a mechanical breakdown: add that alert"]
        if light and out.plan_adjustment_needed:
            return ["easy run without red flags: plan_adjustment_needed must be false"]
        return []

    return await run_agent(
        session,
        llm,
        user_id=user.id,
        agent=AgentName.MECHANICAL_LOAD,
        trigger=AgentTrigger.POST_ACTIVITY,
        run_id=run_id,
        system=prompts.MECHANICAL_LOAD,
        task=LIGHT_TASK if light else "Analyze the activity in the context.",
        context=variable,
        stable_context=ctx,
        cache_prefix=False,  # one-shot: no other call re-reads this prefix
        output_model=MechanicalLoadOutput,
        effort="low" if light else "medium",
        max_tokens=8000 if light else 16000,
        validate=validate,
        activity_id=activity.id,
        model=get_settings().mechanical_load_light_model if light else None,
    )
