#!/usr/bin/env python3
"""Reprice retained trial evidence using runta-cost-eval's accounting rules.

The bundled table is the frozen benchmark basis, not live provider billing.
Pass --pricing for a different table; model entries then match exactly.
"""
import argparse
import json
from pathlib import Path

from cost_accounting import price_usage, usage
from usage_details import extract_usage_details, extract_usage_totals


def calculate(trial_dir, model, harness, pricing, bundled=True):
    paths = sorted((trial_dir / "jobs").rglob("result.json"))
    # Job summaries contain totals for their children. Never charge both, or
    # silently combine retries into the canonical attempt.
    leaves = [p for p in paths if not any(p.parent in q.parents for q in paths if q != p)]
    empty = {"cost_usd": None, "cost_first_cold_usd": None,
             "cost_source": "unavailable", "cache_hit_rate_normalized": None}
    if len(leaves) != 1:
        return {**empty, "cost_unavailable_reason": "missing_or_ambiguous_trial_result"}
    path = leaves[0]
    result = json.loads(path.read_text())
    info = result.get("agent_info") or {}
    model = (info.get("model_info") or {}).get("name") or model
    harness = info.get("name") or harness
    pricing_model = model
    if bundled and model.lower().split("/")[-1] in ("k3", "kimi-k3"):
        pricing_model = "k3"
    tokens = list(usage(result))
    recovered = extract_usage_totals(path.parent / "agent", harness)
    if recovered:
        for i, value in enumerate(recovered):
            if tokens[i] is None:
                tokens[i] = value
    inp, cached, writes, out, reported = tokens
    if reported is None:
        reported = next((result[k] for k in ("total_cost_usd", "total_cost", "cost_usd")
                         if isinstance(result.get(k), (int, float))), None)
    billed, provenance = price_usage(pricing_model, inp, cached, writes, out, pricing)
    source = "price_table" if billed is not None else "agent_reported" if reported is not None else "unavailable"
    actual = billed if billed is not None else reported
    details = extract_usage_details(path.parent / "agent", harness)
    first = details["first_cached"]
    rates = pricing.get("models", {}).get(pricing_model)
    cold = actual + first * (rates["fresh_input"] - rates["cache_read"]) / pricing["unit_tokens"] if actual is not None and first is not None and rates else None
    return {
        "cost_usd": actual, "reported_cost_usd": reported,
        "cost_first_cold_usd": cold, "cost_source": source,
        "pricing": provenance, "cost_basis": pricing.get("version"),
        "input_tokens": inp, "cached_input_tokens": cached,
        "cache_write_tokens": writes, "output_tokens": out,
        "first_turn_input_tokens": details["first_input"],
        "first_turn_cached_tokens": first,
        "cache_hit_rate_normalized": max(0, (cached or 0) - first) / inp if inp and first is not None else None,
        **({"turns": details["calls"]} if details["calls"] else {}),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", type=Path, required=True)
    parser.add_argument("--model", default="")
    parser.add_argument("--harness", default="")
    parser.add_argument("--pricing", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    pricing = json.loads((args.pricing or Path(__file__).with_name("pricing.json")).read_text())
    record = calculate(args.trial, args.model, args.harness, pricing, not args.pricing)
    if args.write:
        path = args.trial / "trial.json"
        trial = json.loads(path.read_text())
        path.write_text(json.dumps({**trial, **record}, indent=2) + "\n")
    else:
        print(json.dumps(record))
