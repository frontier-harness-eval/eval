"""Harbor adapter for the official DSH CLI."""
from harbor.agents.base import BaseAgent
from harbor.agents.installed.base import NonZeroAgentExitCodeError

from .runtime import VERSION, DshRuntime

__all__ = ["DeepSeekHarness", "VERSION"]


class DeepSeekHarness(DshRuntime, BaseAgent):
    exit_error = NonZeroAgentExitCodeError
