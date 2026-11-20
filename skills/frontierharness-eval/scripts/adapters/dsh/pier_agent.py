"""Pier adapter for the official DSH CLI."""
from pier.agents.base import BaseAgent
from pier.agents.installed.base import NonZeroAgentExitCodeError
from pier.agents.network import allowlist_from_urls

from .runtime import DshRuntime


class DeepSeekHarness(DshRuntime, BaseAgent):
    exit_error = NonZeroAgentExitCodeError

    def network_allowlist(self):
        return allowlist_from_urls([self.base_url])

    def inference_env(self, environment, env):
        # Pier connects the task only to its authenticated inference proxy.
        # Node 22 reads that proxy configuration at startup.
        return environment.agent_process_env({**env, "NODE_USE_ENV_PROXY": "1"})
