"""Harbor's MCode adapter with a checkpointed, offline installation step."""

from __future__ import annotations

import hashlib
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
        bundle_sha256: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._bundle_path = Path(bundle_path)
        self._bundle_sha256 = bundle_sha256
        if bundle_sha256 and (
            len(bundle_sha256) != 64
            or any(character not in "0123456789abcdef" for character in bundle_sha256)
        ):
            raise ValueError("bundle_sha256 must be a lowercase SHA-256 digest")
        super().__init__(*args, **kwargs)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        if not self._bundle_path.is_file():
            raise FileNotFoundError(f"MCode runtime bundle not found: {self._bundle_path}")
        actual_sha256 = self._sha256(self._bundle_path)
        if self._bundle_sha256 and actual_sha256 != self._bundle_sha256:
            raise ValueError(
                "MCode runtime bundle digest mismatch: "
                f"expected {self._bundle_sha256}, got {actual_sha256}"
            )

        remote_bundle = "/tmp/frontierharness-mcode-runtime.tar.gz"
        await environment.upload_file(self._bundle_path, remote_bundle)
        quoted_bundle = shlex.quote(remote_bundle)
        remote_digest_check = (
            "printf '%s  %s\\n' "
            f"{shlex.quote(actual_sha256)} {quoted_bundle} | sha256sum -c -; "
        )
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                "command -v sha256sum >/dev/null; command -v tar >/dev/null; "
                f"{remote_digest_check}"
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
