"""Summarise an existing jobs directory without re-running anything.

    python summarize.py jobs/hello-sum-oracle-vs-harness
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

job_dir = Path(sys.argv[1])
by_agent = defaultdict(lambda: {"passed": 0, "total": 0, "cost": 0.0, "priced": 0, "errors": 0})

for result_file in sorted(job_dir.glob("*/result.json")):  # one directory per trial
    trial = json.loads(result_file.read_text())
    agent = trial["agent_info"]["name"]
    rewards = (trial.get("verifier_result") or {}).get("rewards") or {}
    stats = by_agent[agent]
    stats["total"] += 1
    stats["passed"] += rewards.get("reward", 0) >= 1
    cost = (trial.get("agent_result") or {}).get("cost_usd")
    if cost is not None:
        stats["cost"] += cost
        stats["priced"] += 1
    stats["errors"] += trial.get("exception_info") is not None

for agent, s in by_agent.items():
    cost = f"${s['cost']:.4f}" if s["priced"] else "unavailable"
    print(f"{agent:<14} pass {s['passed']}/{s['total']}  errors {s['errors']}  "
          f"reported cost {cost} ({s['priced']}/{s['total']} trials)")
