"""Pier adapter for graff (https://github.com/justrach/codegraff).

Same contract as the Harbor adapter: upload the checkpointed binary, run a
one-shot `graff --json --yolo -p` turn. Pier's per-agent allowlist is what
lets the harness reach the provider on DeepSWE `allow_internet = false` tasks.
"""

from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from typing import Any

from pier.agents.installed.base import BaseInstalledAgent, with_prompt_template
from pier.agents.network import allowlist_from_urls
from pier.environments.base import BaseEnvironment
from pier.models.agent.context import AgentContext
from pier.models.agent.install import AgentInstallSpec, InstallStep
from pier.models.agent.network import NetworkAllowlist

HOST_BINARY = "/work/graff/graff"
REMOTE_BINARY = "/usr/local/bin/graff"
OUTPUT_FILENAME = "graff.jsonl"
PROVIDER_ENV_KEYS = (
    "FIREWORKS_API_KEY",
    "MOONSHOT_API_KEY",
    "OPENROUTER_API_KEY",
)


def native_kimi_model(model: str | None) -> str:
    if not model:
        return "accounts/fireworks/models/kimi-k3"
    for prefix in ("fireworks_ai/", "openrouter/", "moonshot/", "together_ai/", "openai/"):
        if model.startswith(prefix):
            return model[len(prefix) :]
    return model


def provider_env() -> dict[str, str]:
    return {key: os.environ[key] for key in PROVIDER_ENV_KEYS if os.environ.get(key)}


class Graff(BaseInstalledAgent):
    """Checkpointed graff binary, one-shot `--json --yolo -p`."""

    SUPPORTS_ATIF = False
    _OUTPUT_FILENAME = OUTPUT_FILENAME

    def __init__(self, *args: Any, binary_path: str = HOST_BINARY, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._binary_path = binary_path

    @staticmethod
    def name() -> str:
        return "graff"

    def get_version_command(self) -> str | None:
        return f"{REMOTE_BINARY} --version"

    def network_allowlist(self) -> NetworkAllowlist:
        return allowlist_from_urls(
            [],
            default_domains=[
                "api.fireworks.ai",
                "api.moonshot.ai",
                "openrouter.ai",
            ],
        )

    def install_spec(self) -> AgentInstallSpec:
        # Real install uploads the checkpointed binary. Pier requires a non-empty
        # spec; the no-op step is only for the Dockerfile fingerprint.
        return AgentInstallSpec(
            agent_name=self.name(),
            version=self._version,
            steps=[InstallStep(user="root", run="true")],
        )

    async def install(self, environment: BaseEnvironment) -> None:
        host = Path(self._binary_path)
        if not host.is_file():
            raise FileNotFoundError(
                f"graff binary not in the golden checkpoint: {host}"
            )
        await environment.upload_file(host, REMOTE_BINARY)
        quoted = shlex.quote(REMOTE_BINARY)
        await self.exec_as_root(
            environment,
            command=f"chmod 0755 {quoted} && {quoted} --version",
        )

    def populate_context_post_run(self, context: AgentContext) -> None:
        path = self.logs_dir / OUTPUT_FILENAME
        if not path.is_file():
            return
        input_tokens = 0
        cache_tokens = 0
        cost = 0.0
        found = False
        for line in path.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "turn":
                continue
            found = True
            input_tokens += int(event.get("input_tokens") or 0)
            cache_tokens += int(event.get("cache_read_tokens") or 0)
            cost += float(event.get("cost_usd") or 0)
        if not found:
            return
        context.n_input_tokens = input_tokens
        context.n_cache_tokens = cache_tokens
        context.cost_usd = cost

    @with_prompt_template
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        model = native_kimi_model(self.model_name)
        logs = "/logs/agent"
        out = f"{logs}/{OUTPUT_FILENAME}"
        command = (
            f"mkdir -p {shlex.quote(logs)}; "
            f"{shlex.quote(REMOTE_BINARY)} --json --yolo "
            f"--model {shlex.quote(model)} "
            f"-p {shlex.quote(instruction)} "
            f"> {shlex.quote(out)}"
        )
        await self.exec_as_agent(environment, command=command, env=provider_env())
