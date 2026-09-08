"""Harbor's MCode adapter with a checkpointed, offline installation step."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any, override

from harbor.agents.installed.mcode import MCode
from harbor.environments.base import BaseEnvironment


class OfflineMCode(MCode):
    """Install a prebuilt MCode runtime without giving task setup network access."""

    def __init__(
        self,
        *args: Any,
        bundle_path: str = "/work/mcode-runtime.tar.gz",
        **kwargs: Any,
    ) -> None:
        self._bundle_path = Path(bundle_path)
        super().__init__(*args, **kwargs)

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        if not self._bundle_path.is_file():
            raise FileNotFoundError(f"MCode runtime bundle not found: {self._bundle_path}")
        remote_bundle = "/tmp/frontierharness-mcode-runtime.tar.gz"
        await environment.upload_file(self._bundle_path, remote_bundle)
        quoted_bundle = shlex.quote(remote_bundle)
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                "command -v tar >/dev/null; "
                'install_dir="$HOME/.local/mcode"; '
                'rm -rf "$install_dir"; '
                'mkdir -p "$install_dir" "$HOME/.nvm"; '
                f"tar -xzf {quoted_bundle} -C \"$install_dir\"; "
                "printf '%s\\n' "
                "'export NVM_DIR=\"$HOME/.nvm\"' "
                "'export PATH=\"$HOME/.local/mcode/bin:$PATH\"' "
                '> "$HOME/.nvm/nvm.sh"; '
                '. "$HOME/.nvm/nvm.sh"; '
                "node --version; mcode --version"
            ),
        )
