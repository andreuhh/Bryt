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
from app.models import AgentExecutionLog
from app.models.enums import AgentName, AgentRunStatus, AgentTrigger

T = TypeVar("T", bound=BaseModel)

# Returns human-readable violations of deterministic domain rules (empty list = valid)
Validator = Callable[[T], list[str]]

MAX_ATTEMPTS = 2  # first try + one repair round with the violations as feedback


def render_prompt(task: str, context: dict[str, Any]) -> str:
    """Deterministic rendering (sorted keys) keeps identical inputs byte-identical."""
    body = json.dumps(context, sort_keys=True, default=str, ensure_ascii=False, indent=1)
    return f"{task}\n\n<context>\n{body}\n</context>"


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
    effort: Effort,
    max_tokens: int,
    validate: Validator[T] | None = None,
    activity_id: uuid.UUID | None = None,
    plan_id: uuid.UUID | None = None,
) -> tuple[T, AgentExecutionLog]:
    """Runs the agent and ALWAYS persists a log row (success or error). Raises AgentError."""
    log = AgentExecutionLog(
        user_id=user_id,
        agent_name=agent,
        trigger=trigger,
        pipeline_run_id=run_id,
        status=AgentRunStatus.ERROR,
        activity_id=activity_id,
        plan_id=plan_id,
        input_snapshot={"task": task, "context": json.loads(json.dumps(context, default=str))},
        model=llm.model,
    )
    started = time.monotonic()
    feedback = ""
    in_tokens = out_tokens = 0
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
                )
            except AgentOutputError as exc:
                if attempt == MAX_ATTEMPTS:
                    raise
                feedback = (
                    f"\n\nA previous attempt failed: {exc}. Produce a complete, valid output."
                )
                continue

            in_tokens += result.input_tokens or 0
            out_tokens += result.output_tokens or 0
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
        log.input_tokens = in_tokens or None
        log.output_tokens = out_tokens or None
        session.add(log)
        await session.commit()
        await session.refresh(log)
