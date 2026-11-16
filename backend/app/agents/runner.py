"""Single entry point for every agent call: prompt → structured output → domain checks →
AgentExecutionLog. Agents never talk to each other; they read/write the shared state."""

import json
import time
import uuid
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents.llm import AgentOutputError, Effort, LLMClient
from app.core.config import get_settings
from app.models import AgentExecutionLog
from app.models.enums import AgentName, AgentRunStatus, AgentTrigger

T = TypeVar("T", bound=BaseModel)

# Returns human-readable violations of deterministic domain rules (empty list = valid)
Validator = Callable[[T], list[str]]

MAX_ATTEMPTS = 2  # first try + one repair round with the violations as feedback


def _dump(data: dict[str, Any]) -> str:
    """Deterministic rendering (sorted keys) keeps identical inputs byte-identical (cache)."""
    return json.dumps(data, sort_keys=True, default=str, ensure_ascii=False, indent=1)


def render_prefix(stable_context: dict[str, Any]) -> str:
    return f"<athlete_context>\n{_dump(stable_context)}\n</athlete_context>"


def render_prompt(task: str, context: dict[str, Any]) -> str:
    return f"{task}\n\n<context>\n{_dump(context)}\n</context>"


async def run_agent(
    session: AsyncSession,
    llm: LLMClient,
    *,
    user_id: uuid.UUID,
    agent: AgentName,
    trigger: AgentTrigger,
    run_id: uuid.UUID,
    system: str,
    task: str,
    context: dict[str, Any],
    output_model: type[T],
    stable_context: dict[str, Any] | None = None,
    effort: Effort,
    max_tokens: int,
    validate: Validator[T] | None = None,
    activity_id: uuid.UUID | None = None,
    plan_id: uuid.UUID | None = None,
) -> tuple[T, AgentExecutionLog]:
    """Runs the agent and ALWAYS persists a log row (success or error). Raises AgentError."""
    model = get_settings().model_for(agent)
    log = AgentExecutionLog(
        user_id=user_id,
        agent_name=agent,
        trigger=trigger,
        pipeline_run_id=run_id,
        status=AgentRunStatus.ERROR,
        activity_id=activity_id,
        plan_id=plan_id,
        input_snapshot={
            "task": task,
            "stable_context": json.loads(json.dumps(stable_context or {}, default=str)),
            "context": json.loads(json.dumps(context, default=str)),
        },
        model=model,
    )
    prefix = render_prefix(stable_context) if stable_context else None
    started = time.monotonic()
    feedback = ""
    usage = {"input": 0, "output": 0, "cache_creation": 0, "cache_read": 0}
    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            prompt = render_prompt(task + feedback, context)
            try:
                result = await llm.generate(
                    system=system,
                    prompt=prompt,
                    output_model=output_model,
                    effort=effort,
                    max_tokens=max_tokens,
                    cached_prefix=prefix,
                    model=model,
                )
            except AgentOutputError as exc:
                if attempt == MAX_ATTEMPTS:
                    raise
                feedback = (
                    f"\n\nA previous attempt failed: {exc}. Produce a complete, valid output."
                )
                continue

            usage["input"] += result.input_tokens or 0
            usage["output"] += result.output_tokens or 0
            usage["cache_creation"] += result.cache_creation_input_tokens or 0
            usage["cache_read"] += result.cache_read_input_tokens or 0
            log.model = result.model
            violations = validate(result.parsed) if validate else []
            if not violations:
                log.status = AgentRunStatus.SUCCESS
                log.output = result.parsed.model_dump(mode="json")
                return result.parsed, log
            if attempt == MAX_ATTEMPTS:
                raise AgentOutputError("Domain rules violated: " + "; ".join(violations))
            feedback = (
                "\n\nA previous attempt violated these rules, fix them all:\n- "
                + "\n- ".join(violations)
            )
        raise AgentOutputError("unreachable")  # pragma: no cover
    except Exception as exc:  # every failure is recorded, not only AgentError
        log.error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        log.latency_ms = int((time.monotonic() - started) * 1000)
        log.input_tokens = usage["input"] or None
        log.output_tokens = usage["output"] or None
        log.cache_creation_input_tokens = usage["cache_creation"] or None
        log.cache_read_input_tokens = usage["cache_read"] or None
        session.add(log)
        await session.commit()
        await session.refresh(log)
