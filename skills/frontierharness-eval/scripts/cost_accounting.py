"""Token pricing for the frozen benchmark."""
from __future__ import annotations
from typing import Any

def usage(
    result: dict[str, Any],
) -> tuple[int | None, int | None, int | None, int | None, float | None]:
    contexts = []
    if isinstance(result.get("agent_result"), dict):
        contexts.append(result["agent_result"])
    for step in result.get("step_results") or []:
        if isinstance(step.get("agent_result"), dict):
            contexts.append(step["agent_result"])

    def token_total(key: str) -> int | None:
        values = [context.get(key) for context in contexts]
        known = [int(value) for value in values if value is not None]
        return sum(known) if known else None

    input_tokens = token_total("n_input_tokens")
    cached_tokens = token_total("n_cache_tokens")
    output_tokens = token_total("n_output_tokens")
    cache_write_tokens = token_total("n_cache_write_tokens")
    costs = [context.get("cost_usd") for context in contexts]
    known_costs = [float(cost) for cost in costs if cost is not None]
    return (
        input_tokens,
        cached_tokens,
        cache_write_tokens,
        output_tokens,
        sum(known_costs) if known_costs else None,
    )


def price_usage(
    model: str,
    input_tokens: int | None,
    cached_tokens: int | None,
    cache_write_tokens: int | None,
    output_tokens: int | None,
    pricing: dict[str, Any],
) -> tuple[float | None, dict[str, Any] | None]:
    rates = pricing.get("models", {}).get(model)
    if not rates or input_tokens is None or output_tokens is None:
        return None, None
    if input_tokens == 0 and output_tokens == 0:
        return None, None
    cached = cached_tokens or 0
    cache_write = cache_write_tokens or 0
    fresh = max(0, input_tokens - cached - cache_write)
    unit = int(pricing["unit_tokens"])
    cost = (
        fresh * float(rates["fresh_input"])
        + cache_write * float(rates["cache_write"])
        + cached * float(rates["cache_read"])
        + output_tokens * float(rates["output"])
    ) / unit
    return cost, {
        "version": pricing["version"],
        "source": pricing["source"],
        "currency": pricing["currency"],
        "unit_tokens": unit,
        "rates": rates,
    }


