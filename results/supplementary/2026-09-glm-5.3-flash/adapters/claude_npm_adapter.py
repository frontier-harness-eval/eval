"""Install the same pinned Claude CLI via npm after bootstrap CDN TLS failure.

Only installation changes; stock prompts, tools, API configuration and run loop.
"""
from harbor.agents.installed.claude_code import ClaudeCode as HarborClaude
from harbor.agents.installed.node_install import nvm_node_install_snippet
from pier.agents.installed.claude_code import ClaudeCode as PierClaude
from pier.models.agent.install import AgentInstallSpec, InstallStep


def install_command(version):
    if version!='2.1.237':raise ValueError('Pinned original benchmark version required')
    return (
        'set -euo pipefail; '
        'if command -v apk >/dev/null; then node --version && npm --version; else '
        +nvm_node_install_snippet()+'; fi && '
        'npm install -g @anthropic-ai/claude-code@2.1.237 && '
        'mkdir -p "$HOME/.local/bin" && '
        'fh_claude_bin="$(command -v claude)" && '
        'fh_node_dir="$(dirname "$(command -v node)")" && '
        'printf \'#!/bin/bash\nexport PATH="%s:$PATH"\nexec "%s" "$@"\n\' '
        '"$fh_node_dir" "$fh_claude_bin" > "$HOME/.local/bin/claude" && '
        'chmod +x "$HOME/.local/bin/claude" && "$HOME/.local/bin/claude" --version'
    )


class HarborClaudeNpm(HarborClaude):
    async def install(self,environment):
        await self.ensure_system_dependencies(environment,('curl','bash','nodejs','npm'))
        await self.exec_as_agent(environment,command=install_command(self._version))


class PierClaudeNpm(PierClaude):
    def install_spec(self):
        return AgentInstallSpec(agent_name=self.name(),version=self._version,steps=[
            InstallStep(user='root',env={'DEBIAN_FRONTEND':'noninteractive'},
                        run='if command -v apk >/dev/null; then apk add --no-cache curl bash nodejs npm; else apt-get update && apt-get install -y curl bash; fi'),
            InstallStep(user='agent',run=install_command(self._version)),
        ],verification_command=self.get_version_command())
