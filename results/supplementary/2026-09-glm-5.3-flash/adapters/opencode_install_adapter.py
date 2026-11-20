"""Installation-only repair: pinned NVM script downloads instead of Git clone.

Stock OpenCode prompts, tools, configuration and run loop are inherited intact.
"""
from harbor.agents.installed.opencode import OpenCode
from harbor.agents.installed.node_install import nvm_node_install_snippet


class OpenCodeScriptInstall(OpenCode):
    async def install(self, environment):
        if self._version != '1.18.19':
            raise ValueError('This repair is pinned to the original baseline version')
        await self.ensure_system_dependencies(
            environment, ('curl', 'bash', 'coreutils', 'nodejs', 'npm')
        )
        node_install = nvm_node_install_snippet().replace(
            'env -u NODE_VERSION bash', 'env -u NODE_VERSION METHOD=script bash'
        ).replace('curl -o-', 'curl --fail --retry 3 --connect-timeout 30 -o-')
        await self.exec_as_agent(
            environment,
            command=(
                'set -euo pipefail; '
                'if ldd --version 2>&1 | grep -qi musl || '
                '[ -f /etc/alpine-release ]; then '
                'node --version && npm --version; '
                f'else {node_install}; fi && '
                'npm i -g opencode-ai@1.18.19 && opencode --version'
            ),
        )
