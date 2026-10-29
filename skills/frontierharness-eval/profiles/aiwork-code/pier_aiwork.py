"""Run the AiWork.Code (dtcoder) harbor agent through Pier's public interface.

Pier drives the 9 DeepSWE tasks. dtcoder is a compiled binary that honours the
standard HTTPS_PROXY, so — unlike the node-based mcode profile — no request
preload shim is needed: routing dtcoder's exec through Pier's own
BaseInstalledAgent._exec is enough for Pier to inject its authenticated proxy
env. Task execution, resource limits and verification stay entirely with Pier.
"""

from pier.agents.base import BaseAgent
from pier.agents.installed.base import BaseInstalledAgent as PierInstalledAgent
from pier.models.agent.network import NetworkAllowlist

from frontierharness_aiwork import AiworkAgent


class _PierAiwork(AiworkAgent):
    """The harbor dtcoder agent with its exec routed through Pier's plumbing."""

    async def _exec(self, environment, command, **kwargs):
        # AiworkAgent.install()/run() funnel every command through exec_as_root
        # -> self._exec. Delegate to Pier's installed-agent exec so the command
        # runs against the Pier environment with Pier's proxy env applied.
        return await PierInstalledAgent._exec(self, environment, command, **kwargs)


class Aiwork(BaseAgent):
    """Leave execution, limits and verification to Pier; run dtcoder inside it."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._aiwork = _PierAiwork(*args, **kwargs)

    @staticmethod
    def name():
        return "aiwork-code"

    def version(self):
        return self._aiwork.version()

    def network_allowlist(self):
        return NetworkAllowlist(domains=["api.moonshot.cn"])

    async def setup(self, environment):
        await self._aiwork.setup(environment)

    async def run(self, instruction, environment, context):
        try:
            await self._aiwork.run(instruction, environment, context)
        finally:
            self._aiwork.populate_context_post_run(context)
