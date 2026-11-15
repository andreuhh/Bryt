"""LLM access behind a small protocol, so agents are testable without network calls.

AnthropicLLM uses the Messages API with structured outputs (`output_format=<Pydantic model>`,
validated client-side by the SDK), adaptive thinking, explicit effort, streaming (plans can be
long) and server-side refusal fallbacks (`fallbacks="default"`).
"""

from dataclasses import dataclass
from typing import Generic, Literal, Protocol, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings

T = TypeVar("T", bound=BaseModel)

Effort = Literal["low", "medium", "high", "xhigh", "max"]

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AgentError(Exception):
    """Base error of the agent layer (persisted in AgentExecutionLog.error)."""


class AgentUnavailableError(AgentError):
    """API unreachable, rate-limited or misconfigured: retry later."""


class AgentRefusalError(AgentError):
    pass


class AgentOutputError(AgentError):
    """Output truncated or not matching the schema: retryable with feedback."""


@dataclass
class LLMResult(Generic[T]):
    parsed: T
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMClient(Protocol):
    @property
    def model(self) -> str: ...

    async def generate(
        self,
        *,
        system: str,
        prompt: str,
        output_model: type[T],
        effort: Effort,
        max_tokens: int,
    ) -> LLMResult[T]: ...


class AnthropicLLM:
    def __init__(self, model: str | None = None, client: anthropic.AsyncAnthropic | None = None):
        settings = get_settings()
        self._model = model or settings.anthropic_model
        # Empty key → the SDK resolves credentials from the environment / `ant auth login`
        self._client = client or anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key or None
        )

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        *,
        system: str,
        prompt: str,
        output_model: type[T],
        effort: Effort,
        max_tokens: int,
    ) -> LLMResult[T]:
        try:
            async with self._client.beta.messages.stream(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                thinking={"type": "adaptive"},
                output_config={"effort": effort},
                output_format=output_model,
                cache_control={"type": "ephemeral"},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            ) as stream:
                final = await stream.get_final_message()
        except (ValidationError, ValueError) as exc:
            raise AgentOutputError(f"Output does not match {output_model.__name__}: {exc}") from exc
        except anthropic.BadRequestError as exc:
            raise AgentError(f"Bad request: {exc.message}") from exc
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise AgentUnavailableError("Anthropic credentials missing or invalid") from exc
        except anthropic.RateLimitError as exc:
            raise AgentUnavailableError("Anthropic rate limit reached") from exc
        except anthropic.APIStatusError as exc:
            raise AgentUnavailableError(f"Anthropic API error {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise AgentUnavailableError("Anthropic API unreachable") from exc
        except anthropic.AnthropicError as exc:
            raise AgentUnavailableError(str(exc)) from exc
        except TypeError as exc:
            # The SDK raises TypeError when no credential source resolves (no API key,
            # auth token or `ant auth login` profile). Any other TypeError is a real bug.
            if "authentication method" not in str(exc):
                raise
            raise AgentUnavailableError(
                "Anthropic credentials not configured (set ANTHROPIC_API_KEY)"
            ) from exc

        if final.stop_reason == "refusal":
            category = final.stop_details.category if final.stop_details else None
            raise AgentRefusalError(f"Request declined (category: {category})")
        if final.stop_reason == "max_tokens":
            raise AgentOutputError("Output truncated (max_tokens reached)")
        parsed = final.parsed_output
        if parsed is None:
            raise AgentOutputError("Empty structured output")
        return LLMResult(
            parsed=parsed,
            model=final.model,
            input_tokens=final.usage.input_tokens,
            output_tokens=final.usage.output_tokens,
        )


def get_llm() -> LLMClient:
    """FastAPI dependency (overridden in tests)."""
    return AnthropicLLM()
