"""BRYT Coach: conversational access to the shared state.

Proposes plan changes, never applies them (the athlete confirms via POST /plans/adjust)."""

import uuid
from collections.abc import Sequence

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents import prompts
from app.agents.context import athlete_context, dump_activity, local_today, plan_context
from app.agents.llm import LLMClient
from app.agents.runner import run_agent
from app.models import Activity, AgentExecutionLog, User
from app.models.enums import AgentName, AgentRunStatus, AgentTrigger
from app.schemas.agents import CoachChatOutput
from app.schemas.coach import ChatMessage

RECENT_ACTIVITIES = 5
PLAN_DAYS = 14


async def chat(
    session: AsyncSession, llm: LLMClient, user: User, messages: Sequence[ChatMessage]
) -> tuple[CoachChatOutput, AgentExecutionLog]:
    today = local_today(user)
    ctx, _ = await athlete_context(session, user, today)
    ctx |= await plan_context(session, user.id, today, PLAN_DAYS)

    recent = list(
        (
            await session.exec(
                select(Activity)
                .where(Activity.user_id == user.id)
                .order_by(col(Activity.start_time).desc())
                .limit(RECENT_ACTIVITIES)
            )
        ).all()
    )
    analyses = {
        log.activity_id: log.output
        for log in (
            await session.exec(
                select(AgentExecutionLog)
                .where(
                    AgentExecutionLog.user_id == user.id,
                    col(AgentExecutionLog.activity_id).in_([a.id for a in recent]),
                    AgentExecutionLog.status == AgentRunStatus.SUCCESS,
                    col(AgentExecutionLog.agent_name).in_(
                        [AgentName.MECHANICAL_LOAD, AgentName.NUTRITION_RECOVERY]
                    ),
                )
                .order_by(col(AgentExecutionLog.created_at))
            )
        ).all()
        if log.output
    }
    ctx["recent_activities"] = [
        dump_activity(a) | {"latest_analysis_summary": (analyses.get(a.id) or {}).get("summary")}
        for a in recent
    ]

    transcript = "\n".join(
        f"{'Athlete' if m.role == 'user' else 'Coach'}: {m.content}" for m in messages
    )
    return await run_agent(
        session,
        llm,
        user_id=user.id,
        agent=AgentName.COACH_CHAT,
        trigger=AgentTrigger.CHAT,
        run_id=uuid.uuid4(),
        system=prompts.COACH_CHAT,
        task=f"Conversation so far:\n{transcript}\n\nReply to the athlete's last message.",
        context=ctx,
        output_model=CoachChatOutput,
        effort="low",
        max_tokens=8000,
    )
