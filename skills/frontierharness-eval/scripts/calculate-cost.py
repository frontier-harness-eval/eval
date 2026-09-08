#!/usr/bin/env python3
"""Reprice retained trial evidence using the frozen benchmark accounting rules.

The bundled table is the frozen benchmark basis, not live provider billing.
Pass --pricing for a different table; model entries then match exactly.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

from cost_accounting import price_usage, usage
from usage_details import extract_usage_details, extract_usage_totals


def score(result, details, tokens, trial_dir):
    rewards = (result.get("verifier_result") or {}).get("rewards") or {}
    values = [float(v) for v in rewards.values() if v is not None]
    reward = float(rewards["reward"]) if rewards.get("reward") is not None else sum(values) / len(values) if values else None
    # Pier/custom adapters may expose the same verifier outcome at top level.
    if reward is None:
        reward = next((float(result[k]) for k in ("resolved", "is_resolved", "reward", "passed") if result.get(k) is not None), None)
    started = bool((result.get("agent_execution") or {}).get("started_at"))
    observed = bool(details["calls"]) or any(v not in (None, 0) for v in tokens[:4])
    completion_path = trial_dir / "completion.json"
    completion = json.loads(completion_path.read_text()) if completion_path.exists() else {}
    watchdog = completion.get("exit_code") in (124, 137)
    exception = result.get("exception_info") or {}
    timed_out = started and (watchdog or exception.get("exception_type") == "AgentTimeoutError")
    success = reward is not None and reward >= 1 and observed
    status = "success" if success else "failure" if timed_out or (reward is not None and observed) else "infra_invalid"
    if timed_out and reward is None:
        reward = 0.0
    duration = 0.0
    if result.get("started_at") and result.get("finished_at"):
        duration = max(0.0, (datetime.fromisoformat(result["finished_at"].replace("Z", "+00:00")) - datetime.fromisoformat(result["started_at"].replace("Z", "+00:00"))).total_seconds())
    if timed_out and watchdog:
        duration = completion.get("timeout_seconds", completion.get("duration_seconds"))
    usage_observed = any(v not in (None, 0) for v in (tokens[0], tokens[3]))
    execution_evidenced = started or usage_observed
    usage_status = "observed" if usage_observed else "unavailable_after_execution" if execution_evidenced else "not_started"
    reason = None if usage_observed else "timeout_terminated_before_usage_artifact_persisted" if execution_evidenced and timed_out else "usage_artifact_not_observed" if execution_evidenced else "agent_execution_not_started"
    return {"status": status, "success": success, "reward": reward,
            "included_in_efficiency": success, "agent_execution_started": execution_evidenced,
            "usage_observed": usage_observed, "usage_status": usage_status, "usage_unavailable_reason": reason, "completed_with_agent_exception": status in ("success", "failure") and bool(exception),
            "harness_exception": exception or None, "duration_seconds": duration,
            "started_at": result.get("started_at"), "finished_at": result.get("finished_at"),
            "raw_result_path": str(trial_dir / "jobs"),
            "timeout_scope": ("cell" if watchdog else "agent") if timed_out else None}


def calculate(trial_dir, model, harness, pricing, bundled=True, scoring=False):
    paths = sorted((trial_dir / "jobs").rglob("result.json"))
    # Job summaries contain totals for their children. Never charge both, or
    # silently combine retries into the canonical attempt.
    leaves = [p for p in paths if not any(p.parent in q.parents for q in paths if q != p)]
    empty = {"cost_usd": None, "cost_first_cold_usd": None,
             "cost_source": "unavailable", "cache_hit_rate_normalized": None}
    if len(leaves) != 1:
        return {**empty, "cost_unavailable_reason": "missing_or_ambiguous_trial_result", **({"status": "infra_invalid", "success": False, "included_in_efficiency": False} if scoring else {})}
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
        "turns": details["calls"] or None,
        "cache_hit_rate_with_first_turn": (cached or 0) / inp if inp else None,
        "cache_hit_rate": min(1.0, max(0, (cached or 0) - first) / (inp - details["first_input"])) if inp and details["first_input"] and first is not None and inp > details["first_input"] else None,
        **(score(result, details, tokens, trial_dir) if scoring else {}),
        "raw_result_path": str(path),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", type=Path, required=True)
    parser.add_argument("--model", default="")
    parser.add_argument("--harness", default="")
    parser.add_argument("--pricing", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--score", action="store_true", help="Also classify the canonical quality outcome from raw evidence")
    args = parser.parse_args()
    pricing = json.loads((args.pricing or Path(__file__).with_name("pricing.json")).read_text())
    record = calculate(args.trial, args.model, args.harness, pricing, not args.pricing, args.score)
    if args.write:
        path = args.trial / "trial.json"
        trial = json.loads(path.read_text())
        path.write_text(json.dumps({**trial, **record}, indent=2) + "\n")
    else:
        print(json.dumps(record))
