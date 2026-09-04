"""Harbor adapter for graff (https://github.com/justrach/codegraff).

Uploads the checkpointed binary into the task container and runs a one-shot
`graff --json --yolo -p` turn. Networked installs are intentionally avoided:
trial egress does not allow github.com.
"""

from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from typing import Any, override

from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

HOST_BINARY = "/work/graff/graff"
REMOTE_BINARY = "/usr/local/bin/graff"
OUTPUT_FILENAME = "graff.jsonl"
PROVIDER_ENV_KEYS = (
    "FIREWORKS_API_KEY",
    "MOONSHOT_API_KEY",
    "OPENROUTER_API_KEY",
)


def native_kimi_model(model: str | None) -> str:
    """Strip Harbor's LiteLLM provider prefix, leaving graff's model id."""
    if not model:
        return "accounts/fireworks/models/kimi-k3"
    for prefix in ("fireworks_ai/", "openrouter/", "moonshot/", "together_ai/", "openai/"):
        if model.startswith(prefix):
            return model[len(prefix) :]
    return model


def provider_env() -> dict[str, str]:
    return {key: os.environ[key] for key in PROVIDER_ENV_KEYS if os.environ.get(key)}


def apply_turn_metrics(path: Path, context: AgentContext) -> None:
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


class Graff(BaseInstalledAgent):
    """Checkpointed graff binary, one-shot `--json --yolo -p`."""

    _OUTPUT_FILENAME = OUTPUT_FILENAME

    def __init__(self, *args: Any, binary_path: str = HOST_BINARY, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._binary_path = binary_path

    @staticmethod
    @override
    def name() -> str:
        return "graff"

    @override
    def get_version_command(self) -> str | None:
        return f"{REMOTE_BINARY} --version"

    @override
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

    @override
    def populate_context_post_run(self, context: AgentContext) -> None:
        apply_turn_metrics(self.logs_dir / OUTPUT_FILENAME, context)

    @with_prompt_template
    @override
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
