"""Harbor adapter for a CLI coding-agent harness ("my-harness").

Harbor calls install() once per trial inside the fresh task container, then run()
with the task instruction. Everything the agent writes under /logs/agent inside the
container is synced to <trial>/agent/ on the host, where populate_context_post_run()
can read it to report token usage and cost.
"""
import json
import shlex
from typing import override

from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

HARNESS_REPO = "https://github.com/acme/my-harness"
HARNESS_COMMIT = "9f2c1ab"  # pin a commit so every trial runs the same harness


class MyHarness(BaseInstalledAgent):
    @staticmethod
    @override
    def name() -> str:
        return "my-harness"

    @override
    def get_version_command(self) -> str | None:
        return "$HOME/.local/bin/my-harness --version"

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        await self.ensure_system_dependencies(environment, ("curl", "git"))
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                "curl -LsSf https://astral.sh/uv/install.sh | sh; "
                f"$HOME/.local/bin/uv tool install 'git+{HARNESS_REPO}@{HARNESS_COMMIT}'"
            ),
        )

    @override
    @with_prompt_template
    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        if not self.model_name:
            raise ValueError("pass a model with -m, e.g. fireworks_ai/accounts/fireworks/models/kimi-k3")
        api_key = self._get_env("FIREWORKS_API_KEY", "FIREWORKS_AI_API_KEY")
        if not api_key:
            raise ValueError("FIREWORKS_API_KEY is not set (export it or pass --ae)")

        # Raise only when the harness itself crashes; a wrong answer is the
        # verifier's job to score. exec_as_agent raises on a non-zero exit.
        await self.exec_as_agent(
            environment,
            command=(
                "$HOME/.local/bin/my-harness run --yes "
                f"--model {shlex.quote(self.model_name)} "
                f"--prompt {shlex.quote(instruction)} "
                "--usage-file /logs/agent/usage.json "
                "2>&1 | tee /logs/agent/my-harness.log"
            ),
            env={"FIREWORKS_API_KEY": api_key},
            cwd="/app",
        )

    @override
    def populate_context_post_run(self, context: AgentContext) -> None:
        usage_file = self.logs_dir / "usage.json"
        if not usage_file.exists():
            return
        usage = json.loads(usage_file.read_text())
        context.n_input_tokens = usage.get("input_tokens")
        context.n_cache_tokens = usage.get("cached_input_tokens")
        context.n_output_tokens = usage.get("output_tokens")
        context.cost_usd = usage.get("cost_usd")
