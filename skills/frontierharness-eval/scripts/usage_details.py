"""Per-call usage details (turn count, first-call cache stats) per harness.

Per-call accounting for the frozen benchmark.

Trial totals come from agent_result via Harbor's AgentContext; this module
reads the raw harness logs in the trial's agent directory to answer two
fairness questions the totals cannot:

- `calls`: how many model API calls (turns) the task took.
- `first_input` / `first_cached`: the first call's prompt size and cached
  portion — the only cache content a same-family (or same-day) run can
  donate, which the first-cold accounting reprices as fresh.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator, Optional

Detail = dict[str, Optional[int]]


def _empty() -> Detail:
    return {"calls": 0, "first_input": None, "first_cached": None}


def _jsonl(text: str) -> Iterator[dict[str, Any]]:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            yield event


def _detail(usages: list[tuple[int, int]]) -> Detail:
    """Build a Detail from (total_input, cached) per call."""
    if not usages:
        return _empty()
    return {
        "calls": len(usages),
        "first_input": usages[0][0],
        "first_cached": usages[0][1],
    }


def _codex(text: str) -> Detail:
    # Rollout JSONL: token_count payloads carry per-call last_token_usage
    # (input_tokens includes cached reads).
    usages = []
    for event in _jsonl(text):
        payload = event.get("payload") or {}
        if payload.get("type") != "token_count":
            continue
        usage = (payload.get("info") or {}).get("last_token_usage") or {}
        total = int(usage.get("input_tokens") or 0)
        cached = int(usage.get("cached_input_tokens") or 0)
        if total or usage.get("output_tokens"):
            usages.append((total, cached))
    return _detail(usages)


def _claude_code(text: str) -> Detail:
    # Session JSONL: assistant message.usage (input_tokens is fresh-only,
    # cache_read_input_tokens is the cached portion).
    usages = []
    for event in _jsonl(text):
        message = event.get("message") or {}
        if message.get("role") != "assistant":
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        fresh = int(usage.get("input_tokens") or 0)
        cached = int(usage.get("cache_read_input_tokens") or 0)
        if fresh or cached or usage.get("output_tokens"):
            usages.append((fresh + cached, cached))
    return _detail(usages)


def _opencode(text: str) -> Detail:
    # step_finish events: part.tokens {input (fresh), cache.read, output}.
    usages = []
    for event in _jsonl(text):
        if event.get("type") != "step_finish":
            continue
        tokens = (event.get("part") or {}).get("tokens") or {}
        fresh = int(tokens.get("input") or 0)
        cached = int((tokens.get("cache") or {}).get("read") or 0)
        if fresh or cached or tokens.get("output"):
            usages.append((fresh + cached, cached))
    return _detail(usages)


def _pi_style(text: str) -> Detail:
    # pi and omp: message_end events, message.usage with pi-ai conventions
    # (input excludes cacheRead). omp's stream has a leading session header.
    usages = []
    for event in _jsonl(text):
        if event.get("type") != "message_end":
            continue
        message = event.get("message") or {}
        if message.get("role") != "assistant":
            continue
        usage = message.get("usage") or {}
        fresh = int(usage.get("input") or 0)
        cached = int(usage.get("cacheRead") or 0)
        if fresh or cached or usage.get("output"):
            usages.append((fresh + cached, cached))
    return _detail(usages)


def _exo(text: str) -> Detail:
    # exo conversation events: a JSON array; usage rides on `messages`
    # events (OpenAI semantics: prompt_tokens includes cached).
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return _empty()
    events = payload if isinstance(payload, list) else payload.get("events", [])
    usages = []
    for event in events:
        if not isinstance(event, dict):
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else event
        if data.get("type") is not None and data.get("type") != "messages":
            continue
        usage = data.get("usage")
        if not isinstance(usage, dict):
            continue
        total = int(usage.get("prompt_tokens") or 0)
        cached = int(usage.get("prompt_cached_tokens") or 0)
        if total or usage.get("completion_tokens"):
            usages.append((total, cached))
    return _detail(usages)


def _dsh(text: str) -> Detail:
    # assistant/message events: data.usage with pi-ai conventions.
    usages = []
    for event in _jsonl(text):
        if event.get("type") != "assistant/message":
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else event
        usage = data.get("usage")
        if not isinstance(usage, dict):
            continue
        fresh = int(usage.get("inputTokens") or 0)
        cached = int(usage.get("cacheReadTokens") or 0)
        if fresh or cached or usage.get("outputTokens"):
            usages.append((fresh + cached, cached))
    return _detail(usages)


def _kimi_code(text: str) -> Detail:
    # wire.jsonl usage.record events: inputOther fresh + inputCacheRead.
    usages = []
    for event in _jsonl(text):
        if event.get("type") != "usage.record":
            continue
        usage = event.get("usage")
        if not isinstance(usage, dict):
            continue
        fresh = int(usage.get("inputOther") or 0)
        cached = int(usage.get("inputCacheRead") or 0)
        if fresh or cached or usage.get("output"):
            usages.append((fresh + cached, cached))
    return _detail(usages)


def _hermes(text: str) -> Detail:
    # Per-call records from the eval-usage plugin (post_api_request hook):
    # input_tokens is fresh-only, cache_read_tokens the cached portion.
    usages = []
    for event in _jsonl(text):
        fresh = int(event.get("input_tokens") or 0)
        cached = int(event.get("cache_read_tokens") or 0)
        if fresh or cached or event.get("output_tokens"):
            usages.append((fresh + cached, cached))
    return _detail(usages)


def _hermes_totals(text: str) -> tuple[int, int, int, int] | None:
    fresh = cached = cache_write = output = calls = 0
    for event in _jsonl(text):
        event_fresh = int(event.get("input_tokens") or 0)
        event_cached = int(event.get("cache_read_tokens") or 0)
        event_cache_write = int(event.get("cache_write_tokens") or 0)
        event_output = int(event.get("output_tokens") or 0)
        if event_fresh or event_cached or event_cache_write or event_output:
            calls += 1
            fresh += event_fresh
            cached += event_cached
            cache_write += event_cache_write
            output += event_output
    if not calls:
        return None
    return fresh + cached, cached, cache_write, output


# harness name -> (glob relative to the trial agent dir, parser)
REGISTRY: dict[str, tuple[str, Any]] = {
    "codex": ("sessions/**/*.jsonl", _codex),
    "claude-code": ("sessions/projects/*/*.jsonl", _claude_code),
    "opencode": ("opencode.txt", _opencode),
    "pi-responses": ("pi.txt", _pi_style),
    "oh-my-pi": ("omp.txt", _pi_style),
    "exo": ("exo-events.json", _exo),
    "dsh-standard": ("dsh-session.jsonl", _dsh),
    "dsh-ptc": ("dsh-session.jsonl", _dsh),
    "dsh-minimal": ("dsh-session.jsonl", _dsh),
    "dsh-creator": ("dsh-session.jsonl", _dsh),
    "kimi-code": (".kimi-code/sessions/*/*/agents/main/wire.jsonl", _kimi_code),
    "hermes": ("hermes-calls.jsonl", _hermes),
}


def extract_usage_details(agent_dir: Path, harness: str) -> Detail:
    entry = REGISTRY.get(harness)
    if not entry or not agent_dir.exists():
        return _empty()
    pattern, parser = entry
    files = sorted(agent_dir.glob(pattern))
    if not files:
        return _empty()
    try:
        return parser(files[-1].read_text())
    except (OSError, UnicodeDecodeError):
        return _empty()


def extract_usage_totals(
    agent_dir: Path, harness: str
) -> tuple[int, int, int, int] | None:
    """Recover totals when Harbor did not persist the agent context."""
    if harness != "hermes" or not agent_dir.exists():
        return None
    files = sorted(agent_dir.glob("hermes-calls.jsonl"))
    if not files:
        return None
    try:
        return _hermes_totals(files[-1].read_text())
    except (OSError, UnicodeDecodeError):
        return None
