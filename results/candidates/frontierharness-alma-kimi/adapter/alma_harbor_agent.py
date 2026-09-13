"""Harbor external agent that runs Alma (headless) as the harness under evaluation.

Use with ``harbor run … -a alma_harbor_agent:AlmaAgent -m fireworks_ai/accounts/fireworks/models/kimi-k3``
with ``PYTHONPATH`` pointing at this directory. See alma_fh_common.py for the design.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

import alma_fh_common as common


def _alma_version() -> str:
    try:
        pkg = json.loads((common.HERE.parent.parent / "package.json").read_text())
        ver = pkg.get("version", "unknown")
    except Exception:
        ver = "unknown"
    try:
        sha = subprocess.run(["git", "-C", str(common.HERE.parent.parent), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        sha = ""
    return f"{ver}+{sha}" if sha else ver


class AlmaAgent(BaseAgent):
    @staticmethod
    def name() -> str:
        return "alma"

    def version(self) -> str | None:
        return _alma_version()

    async def setup(self, environment: BaseEnvironment) -> None:
        # Alma lives on the runtime host, not in the container; nothing to install
        # there. Bring the server (and the usage proxy) up if the restored runtime
        # does not have them running yet.
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
