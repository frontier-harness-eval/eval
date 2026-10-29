"""Harbor agent for AiWork.Code (agentix / the `dtcoder` CLI), Kimi K3 via Moonshot.

FrontierHarness Eval v1 holds the model constant at Kimi K3 and varies only the
harness. This is the AiWork.Code harness: it uploads a prebuilt `dtcoder` binary with
no network access, points it at Kimi K3 over Moonshot's OpenAI-compatible wire
(``https://api.moonshot.cn/v1``), starts the agent daemon, and drives one
``dtcoder chat --json`` turn per task, teeing the event stream to
``/logs/agent/dtcoder.txt``.

That filename is the glob the upstream ``scripts/usage_details.py`` REGISTRY key
``"aiwork-code"`` reads, and ``name()`` returns ``"aiwork-code"`` so that
``calculate-cost.py`` (which overrides ``--harness`` with ``agent_info.name``)
routes cost parsing to that parser. The two MUST stay in agreement or every
cost field is null.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.trial.paths import EnvironmentPaths

_DST = "/installed-agent/dtcoder"
_BIN = f"{_DST}/dtcoder"
_PLUGIN = f"{_DST}/libagentix_ce_dtdag.so"
_STATE = "/root/.agentix"
_CONFIG = f"{_STATE}/config.json"
_AGENT_ID = "fh"
_SESSION = "t1"
_KEY_ENV = "AGENTIX_CONFIG_MODELS_PRIMARY_API_KEY"
_OUTPUT = "dtcoder.txt"

# Moonshot CN OpenAI-compatible endpoint for Kimi K3 (matches the mcode profile's
# api.moonshot.cn/v1). Overridable via kwargs for a live re-point.
_MOONSHOT_URL = "https://api.moonshot.cn/v1"


class AiworkAgent(BaseInstalledAgent):
    """agentix `dtcoder` driving Kimi K3 over Moonshot's OpenAI-compatible wire."""

    SUPPORTS_ATIF = False
    SUPPORTS_RESUME = False

    def __init__(
        self,
        *args: Any,
        bundle_path: str = "/work/dtcoder",
        plugin_path: str | None = None,
        model_name: str = "openai/kimi-k3",
        provider_url: str = _MOONSHOT_URL,
        provider_api: str = "openai-completions",
        provider_model: str = "kimi-k3",
        thinking_level: str = "high",
        max_output_tokens: int = 131072,
        context_window: int = 1048576,
        version: str = "1.0",
        **kwargs: Any,
    ) -> None:
        self._bundle_path = Path(bundle_path)
        self._plugin_path = Path(plugin_path) if plugin_path else None
        self._provider_url = provider_url
        self._provider_api = provider_api
        self._provider_model = provider_model
        self._thinking_level = thinking_level
        self._max_output_tokens = int(max_output_tokens)
        self._context_window = int(context_window)
        self._version = version
        super().__init__(*args, model_name=model_name, **kwargs)
        if self.model_name != "openai/kimi-k3":
            raise ValueError("FrontierHarness v1 fixes the model at Kimi K3")

    @staticmethod
    def name() -> str:
        # MUST equal the usage_details REGISTRY key; calculate-cost.py:65
        # overrides --harness with this value.
        return "aiwork-code"

    def get_version_command(self) -> str:
        return f"{_BIN} --version"

    async def install(self, environment: BaseEnvironment) -> None:
        if not self._bundle_path.is_file():
            raise FileNotFoundError(f"dtcoder binary not found: {self._bundle_path}")

        await self.exec_as_root(
            environment,
            command=f"mkdir -p {_DST} {_STATE}/plugins && chmod 755 /installed-agent {_DST}",
        )
        await environment.upload_file(str(self._bundle_path), _BIN)
        plugin_setup = ""
        if self._plugin_path and self._plugin_path.is_file():
            await environment.upload_file(str(self._plugin_path), _PLUGIN)
            plugin_setup = f" && cp -f {_PLUGIN} {_STATE}/plugins/"
        await self.exec_as_root(
            environment,
            command=f"chmod +x {_BIN} && chmod -R a+rX {_DST}{plugin_setup}",
        )

        # Kimi K3 over Moonshot's OpenAI-compatible wire. The key is passed by
        # env reference so it never lands in argv or on disk in cleartext.
        # dtcoder forwards the model's *name* as the wire `model` param, so it
        # MUST be the provider's wire id ("kimi-k3", per GET /models) — Moonshot
        # 404s on "openai/kimi-k3". self.model_name stays the harbor-facing label.
        model_block = (
            f'"base_url":"{self._provider_url}","api":"{self._provider_api}",'
            f'"api_key":{{"source":"env","id":"{_KEY_ENV}"}},'
            f'"models":[{{"id":"{self._provider_model}","name":"{self._provider_model}",'
            f'"reasoning":true,"input":["text"],'
            f'"context_window":{self._context_window},"max_tokens":{self._max_output_tokens}}}]'
        )
        patch = (
            '{"models":{'
            f'"primary":{{{model_block}}},'
            f'"backup":{{{model_block}}},'
            f'"fast":{{{model_block}}}'
            "}}"
        )
        setup = (
            f"export AGENTIX_STATE_DIR={_STATE} AGENTIX_CONFIG_PATH={_CONFIG}; "
            f"{_BIN} init --provider-url {shlex.quote(self._provider_url)} "
            f"--provider-api {shlex.quote(self._provider_api)} "
            f"--provider-model {shlex.quote(self._provider_model)} --json && "
            f"echo y | {_BIN} config upgrade && "
            f"printf '%s' {shlex.quote(patch)} > /tmp/aiwork_patch.json && "
            f"{_BIN} config apply /tmp/aiwork_patch.json && "
            f"{_BIN} config set agents.defaults.thinking_level '\"{self._thinking_level}\"' && "
            f"{_BIN} config set agents.defaults.max_tokens {self._max_output_tokens} && "
            f"{_BIN} config set agents.defaults.temperature 1.0 && "
            f"{_BIN} config set agents.defaults.context_engine '\"summarizing\"' && "
            f"{_BIN} config set agents.default_agent '\"{_AGENT_ID}\"' && "
            f"{_BIN} config set tools.exec.ask '\"on-miss\"' && "
            f"({_BIN} config set approval.enabled false || true) && "
            f"{_BIN} config validate"
        )
        await self.exec_as_root(
            environment, command=setup, env={_KEY_ENV: self._get_env(_KEY_ENV) or ""}
        )

        start = (
            f"export AGENTIX_STATE_DIR={_STATE} AGENTIX_CONFIG_PATH={_CONFIG}; "
            f"{_BIN} agent create {_AGENT_ID} --model {shlex.quote(self._provider_model)} --from primary || true; "
            f"{_BIN} agent start {_AGENT_ID}"
        )
        await self.exec_as_root(
            environment, command=start, env={_KEY_ENV: self._get_env(_KEY_ENV) or ""}
        )

    @with_prompt_template
    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        out = (EnvironmentPaths.agent_dir / _OUTPUT).as_posix()
        key = self._get_env(_KEY_ENV) or ""
        env = {_KEY_ENV: key, "INSTR": instruction}
        cmd = (
            f"export AGENTIX_STATE_DIR={_STATE} AGENTIX_CONFIG_PATH={_CONFIG}; "
            f"{_BIN} sessions create --agent {_AGENT_ID} --session {_SESSION} || true; "
            f'DTC_INSTR="$INSTR"; unset INSTR; '
            f"{_BIN} chat --agent {_AGENT_ID} --session {_SESSION} "
            f"--model {shlex.quote(self._provider_model)} --thinking-level {shlex.quote(self._thinking_level)} "
            f'--json -y -m "$DTC_INSTR" 2>&1 | tee {out}'
        )
        await self.exec_as_root(environment, command=cmd, env=env)

    def populate_context_post_run(self, context: AgentContext) -> None:
        """Fill trial-total usage from the dtcoder event stream when Harbor did
        not capture it (a zero-usage trial is scored infra_invalid even at
        reward 1). dtcoder's stream.usage.input_tokens is the FULL prompt
        (fresh + cache_read + cache_write); AgentContext has no cache-write
        field, so — like the mcode profile — n_input_tokens carries
        fresh + cache_read (input_tokens - cache_write_tokens), which keeps the
        derived fresh count correct in cost_accounting.price_usage and leaves
        only the cache-write premium as an accepted lower bound."""
        super().populate_context_post_run(context)
        if context.n_input_tokens is not None:
            return
        output = self.logs_dir / _OUTPUT
        if not output.exists():
            return
        data = None
        for line in output.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and (event.get("event") or {}).get("name") == "stream.usage":
                data = event.get("data")
        if not isinstance(data, dict):
            return
        # Kimi's OpenAI-completions wire (and the live Moonshot endpoint) reports
        # cache_read/cache_write as null; only anthropic-messages fills them. A
        # null/absent cache field means "no cache this turn" — i.e. 0 — not "no
        # usage", so requiring it would null every field and score a reward-1
        # trial infra_invalid. Require only the two counts every provider returns.
        if not all(isinstance(data.get(k), int) and data[k] >= 0
                   for k in ("input_tokens", "output_tokens")):
            return

        def _count(key: str) -> int:
            value = data.get(key)
            return value if isinstance(value, int) and value >= 0 else 0

        context.n_input_tokens = max(data["input_tokens"] - _count("cache_write_tokens"), 0)
        context.n_cache_tokens = _count("cache_read_tokens")
        context.n_output_tokens = data["output_tokens"]
        context.metadata = {**(context.metadata or {}), "aiwork_usage": data}
