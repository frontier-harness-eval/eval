"""Pier external agent that runs Alma (headless) as the harness under evaluation.

Use with ``pier run … --agent-import-path alma_pier_agent:AlmaAgent --model fireworks_ai/accounts/fireworks/models/kimi-k3``
with ``PYTHONPATH`` pointing at this directory. DeepSWE tasks run air-gapped
(``network_mode: none``); that is fine here because Alma runs on the host and
only enters the container through ``docker exec``.
"""

from __future__ import annotations

from pier.agents.base import BaseAgent
from pier.environments.base import BaseEnvironment
from pier.models.agent.context import AgentContext

import alma_fh_common as common
from alma_harbor_agent import _alma_version


class AlmaAgent(BaseAgent):
    SUPPORTS_ATIF = False
    SUPPORTS_WINDOWS = False

    @staticmethod
    def name() -> str:
        return "alma"

    def version(self) -> str | None:
        return _alma_version()

    async def setup(self, environment: BaseEnvironment) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        common.ensure_server(self.logs_dir / "alma-ensure.log")

    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:
        await common.drive(
            instruction=instruction,
            session_id=environment.session_id,
            model_name=self.model_name,
            logs_dir=self.logs_dir,
            context=context,
            logger=self.logger,
        )
