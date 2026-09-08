"""Run Harbor's MCode integration through Pier's public agent interface."""

from pathlib import Path

from pier.agents.base import BaseAgent
from pier.agents.installed.base import BaseInstalledAgent
from pier.models.agent.network import NetworkAllowlist

from mcode_kimi_profile import ConfiguredMCode


class _PierMCode(ConfiguredMCode):
    async def install(self, environment):
        folder = Path(__file__).parent
        await environment.upload_file(folder / "undici-8.10.2.tgz", "/tmp/pier-undici.tgz")
        await self.exec_as_agent(environment, command=(
            "mkdir -p /tmp/harbor-mcode/pier-network && "
            "tar -xzf /tmp/pier-undici.tgz -C /tmp/harbor-mcode/pier-network"
        ))
        await environment.upload_file(folder / "pier-proxy.cjs", "/tmp/harbor-mcode/pier-proxy.cjs")
        await super().install(environment)

    async def _exec(self, environment, command, **kwargs):
        # The preload is command-local; tools can still inherit Pier's proxy env.
        if "mcode exec " in command:
            command = command.replace("mcode exec ",
                'node --require /tmp/harbor-mcode/pier-proxy.cjs '
                '"$HOME/.local/mcode/lib/node_modules/@minimax-ai/code/cli.js" exec ', 1)
        return await BaseInstalledAgent._exec(self, environment, command, **kwargs)


class MCode(BaseAgent):
    """Leave task execution, resource limits and verification to Pier."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mcode = _PierMCode(*args, **kwargs)

    @staticmethod
    def name():
        return "mcode"

    def version(self):
        return self._mcode.version()

    def network_allowlist(self):
        return NetworkAllowlist(domains=["api.moonshot.cn"])

    async def setup(self, environment):
        await self._mcode.setup(environment)

    async def run(self, instruction, environment, context):
        try:
            await self._mcode.run(instruction, environment, context)
        finally:
            self._mcode.populate_context_post_run(context)
