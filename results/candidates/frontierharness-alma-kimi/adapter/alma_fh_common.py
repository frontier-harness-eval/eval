"""Shared logic for the Harbor and Pier adapters that run Alma as a FrontierHarness
harness.

Alma is a server application: it stays on the Runta runtime host and reaches the
task container through Alma's remote-host stack via the ssh → docker-exec shim.
The adapters only (1) make sure the Alma server is up, (2) work out the task
container's name, (3) hand the instruction to ``alma-drive.mjs`` and (4) copy the
token/usage results into the runner's AgentContext.

Everything here is standard library only: the module is imported inside the
isolated ``uv tool`` environments of Harbor and Pier.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DRIVER = HERE / "alma-drive.mjs"

# Fireworks list price for Kimi K3 (USD per million tokens): input, cached
# input, output. Overridable so a different provider's price sheet can be used
# without editing code; the values used are echoed into every result file.
_prices = os.environ.get("ALMA_FH_PRICES", "3,0.30,15").split(",")
PRICE_INPUT, PRICE_CACHED, PRICE_OUTPUT = (float(x) for x in _prices)

PORT = os.environ.get("ALMA_FH_PORT", "23100")
PROVIDER_ID = os.environ.get("ALMA_FH_PROVIDER_ID", "fireworks")
NODE_BIN_FOR_CONTAINERS = os.environ.get("ALMA_FH_NODE_BIN", "/work/alma/node-linux-x64")
# Agent budget inside the official 5400 s wrapper (`timeout 5400 pier run`).
# That wrapper starts before the checkpoint restore/build and also covers the
# verifier and artifact export, so an agent allowed the full 5400 s is killed
# mid-work and never scored (README deviation 13). Observed non-agent overhead
# per trial in the first two full runs: 84-175 s. 5000 leaves 400 s.
AGENT_TIMEOUT_SEC = os.environ.get("ALMA_FH_TIMEOUT_SEC", "5000")


def node_executable() -> str:
    node = os.environ.get("ALMA_FH_NODE") or shutil.which("node")
    if not node:
        raise RuntimeError("node not found on PATH; run install-alma.sh first")
    return node


def sanitize_project_name(name: str) -> str:
    """Mirror of Harbor/Pier's docker compose project-name sanitizer."""
    name = name.lower()
    if not re.match(r"^[a-z0-9]", name):
        name = "0" + name
    return re.sub(r"[^a-z0-9_-]", "-", name)


def alma_model(model_name: str | None) -> str:
    """Map the runner's LiteLLM-style route (fireworks_ai/accounts/…/kimi-k3) to
    Alma's providerId:modelId reference."""
    if not model_name:
        raise RuntimeError("a model is required (-m fireworks_ai/accounts/fireworks/models/kimi-k3)")
    model_id = model_name.split("/", 1)[1] if "/" in model_name else model_name
    return f"{PROVIDER_ID}:{model_id}"


def find_container(session_id: str) -> str:
    """The compose service is called ``main`` in both Harbor and Pier, so the task
    container is ``<sanitized session>-main-1``. Confirm against ``docker ps`` so a
    renamed service fails loudly instead of driving the wrong container."""
    project = sanitize_project_name(session_id)
    expected = f"{project}-main-1"
    try:
        out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return expected
    names = [n for n in out.split() if n.startswith(f"{project}-main-")]
    if expected in names or not names:
        return expected
    return sorted(names)[0]


def container_workdir(container: str, default: str = "/app") -> str:
    try:
        out = subprocess.run(
            ["docker", "inspect", "-f", "{{.Config.WorkingDir}}", container], capture_output=True, text=True, timeout=60
        ).stdout.strip()
    except Exception:
        out = ""
    return out or default


def ensure_server(log_path: Path) -> None:
    with open(log_path, "a") as log:
        subprocess.run([node_executable(), str(DRIVER), "ensure-server", "--port", PORT], check=True, stdout=log, stderr=log, timeout=300)


def cost_usd(tokens: dict[str, Any]) -> float:
    uncached = max(0, int(tokens.get("input", 0)) - int(tokens.get("cached", 0)))
    return (
        uncached * PRICE_INPUT + int(tokens.get("cached", 0)) * PRICE_CACHED + int(tokens.get("output", 0)) * PRICE_OUTPUT
    ) / 1_000_000


def fill_context(context: Any, result_path: Path) -> dict[str, Any] | None:
    """Populate the runner's AgentContext from the driver's result JSON."""
    if not result_path.exists():
        return None
    data = json.loads(result_path.read_text())
    tokens = data.get("tokens") or {}
    if tokens:
        context.n_input_tokens = int(tokens.get("input", 0))
        context.n_cache_tokens = int(tokens.get("cached", 0))
        context.n_output_tokens = int(tokens.get("output", 0))
        context.cost_usd = round(cost_usd(tokens), 6)
    if data.get("steps") is not None and hasattr(context, "n_agent_steps"):
        context.n_agent_steps = int(data["steps"])
    context.metadata = {
        "alma_thread_id": data.get("threadId"),
        "finished": data.get("finished"),
        "timed_out": data.get("timedOut"),
        "error": data.get("error"),
        "agent_seconds": data.get("agentSeconds"),
        "steps": data.get("steps"),
        "usage_source": data.get("usageSource"),
        "tokens": tokens,
        "proxy_usage": data.get("proxyUsage"),
        "prices_per_million": {"input": PRICE_INPUT, "cached": PRICE_CACHED, "output": PRICE_OUTPUT},
        "node_source": data.get("nodeSource"),
    }
    return data


async def drive(*, instruction: str, session_id: str, model_name: str | None, logs_dir: Path, context: Any, logger: Any) -> None:
    """Run one trial through Alma. Raises only on harness/infrastructure failure
    (the runner retries those); a task the agent simply got wrong returns normally."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    instruction_file = logs_dir / "instruction.md"
    instruction_file.write_text(instruction)
    result_path = logs_dir / "alma-result.json"
    driver_log = logs_dir / "alma-drive.log"
    container = find_container(session_id)
    workdir = container_workdir(container)
    model = alma_model(model_name)
    label = f"fh:{session_id}"[:80]
    argv = [
        node_executable(),
        str(DRIVER),
        "run",
        "--port", PORT,
        "--model", model,
        "--container", container,
        "--workdir", workdir,
        "--instruction-file", str(instruction_file),
        "--out", str(result_path),
        "--timeout-sec", AGENT_TIMEOUT_SEC,
        "--node-bin", NODE_BIN_FOR_CONTAINERS,
        "--label", label,
    ]
    logger.info("alma: driving container %s (workdir %s) with %s", container, workdir, model)
    with open(driver_log, "a") as log:
        proc = await asyncio.create_subprocess_exec(*argv, stdout=log, stderr=log)
        try:
            rc = await proc.wait()
        except asyncio.CancelledError:
            # Runner timeout: ask the driver to stop the generation and export
            # what it has, then re-raise so the runner records the timeout.
            logger.warning("alma: cancelled, stopping generation in %s", container)
            try:
                proc.send_signal(signal.SIGTERM)
                await asyncio.wait_for(proc.wait(), timeout=45)
            except Exception:
                proc.kill()
            fill_context(context, result_path)
            raise
    data = fill_context(context, result_path)
    if data is None:
        raise RuntimeError(f"alma driver produced no result (exit {rc}); see {driver_log}")
    if data.get("error") and not data.get("threadId"):
        # Never got as far as a thread: provider/config/infra fault, worth a retry.
        raise RuntimeError(f"alma driver failed before the turn started: {data['error']}")
    logger.info(
        "alma: finished=%s timed_out=%s steps=%s tokens=%s", data.get("finished"), data.get("timedOut"), data.get("steps"), data.get("tokens")
    )


# ── post-run summary (called by run-task.sh) ─────────────────────────────────
def _reward_of(verifier_result: dict[str, Any] | None) -> float | None:
    rewards = (verifier_result or {}).get("rewards") or {}
    if not rewards:
        return None
    if "reward" in rewards:
        return float(rewards["reward"])
    if "resolved" in rewards:
        return float(rewards["resolved"])
    return float(next(iter(rewards.values())))


def summarize(jobs_dir: Path) -> dict[str, Any]:
    """Flatten the runner's nested result.json into one readable document
    (reward, cost_usd, n_steps, cache_hit_rate, exception_info). Values come
    straight from the runner's own result document; nothing here re-judges the
    task. This is evidence for humans only: the official scorer reads the
    runner's leaf result.json itself, and it treats a second result.json
    anywhere under {jobs} as an ambiguous trial, so the summary must NOT be
    written under that name (see the writer below)."""
    results = [
        p
        for p in jobs_dir.rglob("result.json")
        if "00-summary" not in p.parts and "alma-thread" not in p.parts
    ]
    results.sort(key=lambda p: p.stat().st_mtime)
    summary: dict[str, Any] = {"source": None, "reward": None, "harness": "alma"}
    for p in results:
        try:
            doc = json.loads(p.read_text())
        except Exception:
            continue
        if not isinstance(doc, dict) or "agent_result" not in doc and "verifier_result" not in doc:
            continue
        agent = doc.get("agent_result") or {}
        meta = agent.get("metadata") or {}
        tokens = meta.get("tokens") or {}
        n_in = int(agent.get("n_input_tokens") or 0)
        n_cached = int(agent.get("n_cache_tokens") or 0)
        summary = {
            "source": str(p.relative_to(jobs_dir)),
            "harness": "alma",
            "reward": _reward_of(doc.get("verifier_result")),
            "cost_usd": agent.get("cost_usd"),
            "n_steps": meta.get("steps") if meta.get("steps") is not None else agent.get("n_agent_steps"),
            "n_input_tokens": n_in,
            "n_cache_tokens": n_cached,
            "n_output_tokens": agent.get("n_output_tokens"),
            "cache_hit_rate": (n_cached / n_in) if n_in else None,
            "agent_finished": meta.get("finished"),
            "agent_timed_out": meta.get("timed_out"),
            "agent_seconds": meta.get("agent_seconds"),
            "proxy_usage": meta.get("proxy_usage"),
            "prices_per_million": meta.get("prices_per_million"),
            "alma_thread_id": meta.get("alma_thread_id"),
            "tokens": tokens,
        }
        if doc.get("exception_info"):
            summary["exception_info"] = doc["exception_info"]
    return summary


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3 and sys.argv[1] == "summarize":
        jobs = Path(sys.argv[2])
        out_dir = jobs / "00-summary"
        out_dir.mkdir(parents=True, exist_ok=True)
        s = summarize(jobs)
        # Deliberately not "result.json": calculate-cost.py globs every
        # result.json under {jobs} and scores the trial infra_invalid when more
        # than one leaf turns up.
        (out_dir / "alma-summary.json").write_text(json.dumps(s, indent=1))
        print(json.dumps(s, indent=1))
    else:
        print("usage: alma_fh_common.py summarize <jobs-dir>", file=sys.stderr)
        sys.exit(2)
