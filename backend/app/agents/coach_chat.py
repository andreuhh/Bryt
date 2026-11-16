"""BRYT Coach: conversational access to the shared state.

Proposes plan changes, never applies them (the athlete confirms via POST /plans/adjust).
Cost guardrails: a daily message quota checked before any LLM call, and the whole shared-state
context sent as the cached prefix, so follow-up turns of a conversation re-read it from cache."""

import uuid
from collections.abc import Sequence
from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents import prompts
from app.agents.context import (
    athlete_context,
    dump_activity,
    local_today,
    plan_context,
    wellness_context,
)
from app.agents.llm import AgentError, LLMClient
from app.agents.runner import run_agent
from app.core.config import get_settings
from app.models import Activity, AgentExecutionLog, User
from app.models.enums import AgentName, AgentRunStatus, AgentTrigger
from app.schemas.agents import CoachChatOutput
from app.schemas.coach import ChatMessage, ChatQuota

RECENT_ACTIVITIES = 5
PLAN_DAYS = 14


class ChatQuotaExceededError(AgentError):
    """Daily message quota used up: no LLM call is made."""


async def chat_quota(session: AsyncSession, user: User) -> ChatQuota:
    """Successful coach replies since local midnight (failed calls don't count)."""
    tz = ZoneInfo(user.timezone)
    midnight = datetime.combine(local_today(user), time.min, tzinfo=tz)
    used = (
        await session.exec(
            select(func.count())
            .select_from(AgentExecutionLog)
            .where(
                AgentExecutionLog.user_id == user.id,
                AgentExecutionLog.agent_name == AgentName.COACH_CHAT,
                AgentExecutionLog.status == AgentRunStatus.SUCCESS,
                col(AgentExecutionLog.created_at) >= midnight,
            )
        )
    ).one()
    limit = get_settings().chat_daily_limit
    return ChatQuota(limit=limit, used=used, remaining=max(limit - used, 0))


async def chat(
    session: AsyncSession, llm: LLMClient, user: User, messages: Sequence[ChatMessage]
) -> tuple[CoachChatOutput, AgentExecutionLog]:
    if (await chat_quota(session, user)).remaining == 0:
        raise ChatQuotaExceededError("Daily coach message limit reached")
    today = local_today(user)
    ctx, _ = await athlete_context(session, user, today)
    variable = await plan_context(session, user.id, today, PLAN_DAYS)

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
    variable["wellness"] = await wellness_context(session, user.id, today)
    variable["recent_activities"] = [
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
        # Everything but the transcript is the cached prefix: it doesn't change between the
        # turns of a conversation (same day, no new activity), so turn 2+ read it from cache.
        context={},
        stable_context=ctx | variable,
        output_model=CoachChatOutput,
        effort="low",
        max_tokens=8000,
    )
