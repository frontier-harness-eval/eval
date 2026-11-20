"""Build the official Linux DSH package once per workspace, platform and recipe."""
import fcntl
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
BUILDER = "node:22-slim@sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee"


def prepare_bundle(platform: str) -> Path:
    if platform not in {"linux/amd64", "linux/arm64"}:
        raise ValueError(f"Unsupported DSH platform {platform}")
    digest = hashlib.sha256(BUILDER.encode())
    for name in ("package.json", "pnpm-lock.yaml", "build.sh"):
        digest.update((HERE / name).read_bytes())
    cache = Path(".fh-local/dsh") / platform.split("/")[1] / digest.hexdigest()
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / "dsh.tgz"
    with (cache / "build.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not archive.is_file():
            with tempfile.TemporaryDirectory(dir=cache) as staging:
                tmp = Path(staging) / "dsh.tgz"
                with tmp.open("wb") as output:
                    subprocess.run(
                        ["docker", "run", "--rm", "--platform", platform,
                         "--volume", f"{HERE}:/recipe:ro", BUILDER, "bash", "/recipe/build.sh"],
                        check=True, stdout=output,
                    )
                os.replace(tmp, archive)
    return archive.resolve()
