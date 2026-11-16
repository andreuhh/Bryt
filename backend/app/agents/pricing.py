"""Claude API list prices → cost of each agent execution (AgentExecutionLog.cost_usd).

Prices in $ per million tokens, prompts up to 100K tokens (Haiku 5.5 doubles beyond: BRYT
prompts stay far below). Cache writes use the 5-minute TTL (1.25x input). Update the table
when Anthropic changes prices or a new model is configured: unknown models get no cost.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_write: float
    cache_read: float


PRICES: dict[str, Price] = {
    "claude-opus-5-5": Price(input=4.0, output=20.0, cache_write=5.0, cache_read=0.20),
    "claude-sonnet-5-5": Price(input=2.0, output=10.0, cache_write=2.5, cache_read=0.20),
    "claude-haiku-5-5": Price(input=0.10, output=0.50, cache_write=0.125, cache_read=0.01),
}


def cost_usd(
    model: str,
    *,
    input_tokens: int | None,
    output_tokens: int | None,
    cache_creation_input_tokens: int | None,
    cache_read_input_tokens: int | None,
) -> float | None:
    """Cost of one execution (all attempts); None for a model missing from PRICES."""
    price = PRICES.get(model)
    if price is None:
        return None
    total = (
        (input_tokens or 0) * price.input
        + (output_tokens or 0) * price.output
        + (cache_creation_input_tokens or 0) * price.cache_write
        + (cache_read_input_tokens or 0) * price.cache_read
    )
    return round(total / 1_000_000, 6)
