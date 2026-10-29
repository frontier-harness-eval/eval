"""Harbor / Pier InstalledAgent adapter for AiWork (agentix `dtcoder` binary).

Rewritten for modern dtcoder (v1.264xx master): the legacy
`agents.defaults.permission_mode` / `approval.*` / `daemon.*` config paths were
retired, and headless one-shot execution is now `dtcoder __print` with `-y`
(auto-approve). This adapter drives ONE `__print` run to completion per task and
dumps its stream-json to /logs/agent/print.jsonl, which the FrontierHarness
`usage_details._aiwork` parser reads for per-call tokens (cost / cache / turns).

Model = MaaS kimi-k3 over anthropic-messages (openai-responses replays reasoning
content -> dtcoder serde crash; anthropic-messages is the vetted MaaS path).

Harbor:  -a aiwork_agent:AiworkAgent   (Terminal-Bench, local docker)
Pier:    change the 3 imports to the pier.* equivalents + add network_allowlist.

Usage (Harbor):
  PYTHONPATH=/home/fhe-eval/fh-agent harbor run -d terminal-bench@2.0 -i <task> \
    -a aiwork_agent:AiworkAgent \
    --ak dtcoder_bin=/home/fhe-eval/dtcoder-bin/dtcoder \
    --ak model=kimi-k3 --ak thinking_level=high \
    --ae AGENTIX_CONFIG_MODELS_PRIMARY_API_KEY=sk-...
"""

import os
import shlex
from pathlib import Path
from typing import Any, override

from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

_REMOTE_BIN = "/usr/local/bin/dtcoder"
_STATE_DIR = "/root/.agentix"
_AGENT_LOG = "/logs/agent"
_AID = "tb"
_PRINT_JSONL = f"{_AGENT_LOG}/print.jsonl"
_PRINT_ERR = f"{_AGENT_LOG}/print.err"

_MAAS_FALLBACK_IPS = ["<redacted-ip-1>", "<redacted-ip-2>"]

_UV_PRELOAD_TARBALL = os.environ.get("DTCODER_UV_PRELOAD", "/tmp/uv-preload.tar.gz")
_UV_PRELOAD_REMOTE = "/tmp/uv-preload.tar.gz"

_RULES = (
    "\n\n---\n"
    "Operating rules for this task:\n"
    "- Complete EVERY requirement end to end. Do not stop after a partial solution.\n"
    "- Create every file / make every change at the EXACT paths requested.\n"
    "- Before finishing, re-read the task and verify each requirement is actually "
    "satisfied (files exist at the right paths, scripts run and produce the expected "
    "output). Fix anything missing.\n"
    "- When everything is done and verified, reply with DONE."
)

_CAPTURE_DOGFOOD_TMPL = r"""
set +e
SRC=/root/.agentix/artifacts/dogfooding
DST=/logs/agent/dogfood
mkdir -p "$DST"
if [ -d "$SRC" ]; then
  cp -a "$SRC/." "$DST/raw/" 2>/dev/null || { mkdir -p "$DST/raw"; cp -r "$SRC/." "$DST/raw/" 2>/dev/null; }
fi
find "$DST" -type f \( -name '*.json' -o -name '*.txt' -o -name '*.md' -o -name '*.jsonl' \) -print0 2>/dev/null \
  | xargs -0 -r sed -i -E \
      -e 's/sk-[A-Za-z0-9]{20,}/sk-REDACTED/g' \
      -e 's/(Bearer )[A-Za-z0-9._-]{16,}/\1REDACTED/g' \
      -e 's/("(api_key|apiKey|authorization|Authorization|x-api-key|auth_token|token)"[[:space:]]*:[[:space:]]*")[^"]+/\1REDACTED/g' \
      2>/dev/null
true
"""


class AiworkAgent(BaseInstalledAgent):
    @staticmethod
    @override
    def name() -> str:
        return "aiwork"

    def __init__(
        self,
        logs_dir: Path,
        dtcoder_bin: str | None = None,
        provider_url: str = "https://<internal-gateway-host>/v1",
        provider_api: str = "anthropic-messages",
        model: str | None = None,
        thinking_level: str | None = "high",
        max_tokens: int | None = None,
        api_key_env: str = "AGENTIX_CONFIG_MODELS_PRIMARY_API_KEY",
        timeout_sec: int = 5400,
        *args: Any,
        **kwargs: Any,
    ):
        self._dtcoder_bin = dtcoder_bin or os.environ.get("DTCODER_BIN")
        self._provider_url = provider_url
        self._provider_api = provider_api
        self._model = model
        self._thinking_level = (str(thinking_level).strip() if thinking_level else None) or None
        self._max_tokens = int(max_tokens) if max_tokens else None
        self._api_key_env = api_key_env
        self._timeout_sec = int(timeout_sec)
        super().__init__(logs_dir, *args, **kwargs)

    def _resolve_model(self) -> str:
        if self._model:
            return self._model
        mn = getattr(self, "model_name", None)
        if mn:
            return mn.split("/", 1)[1] if "/" in mn else mn
        return "kimi-k3"

    def _resolve_key(self) -> str:
        key = self._get_env(self._api_key_env) or os.environ.get(self._api_key_env, "")
        if not key:
            raise RuntimeError(
                f"aiwork: MaaS API key not found in env '{self._api_key_env}'. "
                f"Pass it via `--ae {self._api_key_env}=sk-...`."
            )
        return key

    def _env(self) -> dict[str, str]:
        key = self._resolve_key()
        return {
            "AGENTIX_STATE_DIR": _STATE_DIR,
            self._api_key_env: key,
            "FAST_API_KEY": key,
            "BACKUP_API_KEY": key,
        }

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        if not self._dtcoder_bin or not Path(self._dtcoder_bin).is_file():
            raise RuntimeError(
                f"aiwork: binary not found at '{self._dtcoder_bin}'. "
                f"Pass `--ak dtcoder_bin=/abs/path/to/dtcoder`."
            )
        await environment.upload_file(self._dtcoder_bin, _REMOTE_BIN)
        await self.exec_as_root(environment, command=f"chmod +x {_REMOTE_BIN}")

        # Pin MaaS host IPs into /etc/hosts (best-effort; DNS-independent provider start).
        # ONLY for the internal gateway host: its internal DNS is flaky and the fallback IPs are
        # specific to the internal gateway. For any other provider (e.g. official Kimi api.moonshot.cn) we
        # must NOT pin — mapping a public host to the internal gateway IPs would break TLS/routing; the
        # TB container has public egress + working DNS, so rely on normal resolution.
        try:
            from urllib.parse import urlparse as _urlparse
            import socket as _socket
            _maas_host = _urlparse(self._provider_url).hostname or "<internal-gateway-host>"
            if _maas_host == "<internal-gateway-host>":
                _ips = []
                try:
                    for _ai in _socket.getaddrinfo(_maas_host, 443, _socket.AF_INET, _socket.SOCK_STREAM):
                        _ip = _ai[4][0]
                        if _ip not in _ips:
                            _ips.append(_ip)
                except Exception:
                    pass
                for _fb in _MAAS_FALLBACK_IPS:
                    if _fb not in _ips:
                        _ips.append(_fb)
                if _ips:
                    _cmds = " ; ".join(
                        "grep -qF {q} /etc/hosts || echo {q} >> /etc/hosts".format(
                            q=shlex.quote(_ip + ' ' + _maas_host)
                        )
                        for _ip in _ips
                    )
                    await self.exec_as_root(environment, command=_cmds)
        except Exception:
            pass

        # Best-effort offline uv preload for verifiers (skipped if tarball absent).
        if Path(_UV_PRELOAD_TARBALL).is_file():
            await environment.upload_file(_UV_PRELOAD_TARBALL, _UV_PRELOAD_REMOTE)
            await self.exec_as_root(
                environment,
                command=(
                    "mkdir -p /root/.local/bin /root/.local/share/uv/python && "
                    f"tar xzf {_UV_PRELOAD_REMOTE} -C /root && "
                    "chmod +x /root/.local/bin/uv /root/.local/bin/uvx /root/.local/bin/env"
                ),
            )

        key = self._resolve_key()
        model = self._resolve_model()
        env = {"AGENTIX_STATE_DIR": _STATE_DIR}

        init_cmd = (
            f"{_REMOTE_BIN} init "
            f"--provider-url {shlex.quote(self._provider_url)} "
            f"--provider-key {shlex.quote(key)} "
            f"--provider-api {self._provider_api} "
            f"--provider-model {shlex.quote(model)}"
        )
        res = await environment.exec(command=init_cmd, env=env, timeout_sec=120)
        if res.return_code != 0:
            raise RuntimeError(
                f"dtcoder init failed (rc={res.return_code}): "
                f"{self._truncate_output(res.stderr or res.stdout)}"
            )

        # Optional per-call output cap (valid path in modern schema).
        if self._max_tokens:
            r = await environment.exec(
                command=f"{_REMOTE_BIN} config set agents.defaults.max_tokens {self._max_tokens}",
                env=env, timeout_sec=60,
            )
            if r.return_code != 0:
                self.logger.warning(
                    "aiwork: config set max_tokens rc=%s: %s",
                    r.return_code, self._truncate_output(r.stderr or r.stdout),
                )

        res = await environment.exec(
            command=f"{_REMOTE_BIN} agent create {_AID}", env=env, timeout_sec=60
        )
        if res.return_code != 0 and "already" not in (res.stderr or res.stdout).lower():
            raise RuntimeError(
                f"dtcoder agent create failed (rc={res.return_code}): "
                f"{self._truncate_output(res.stderr or res.stdout)}"
            )

    @override
    def get_version_command(self) -> str | None:
        return f"{_REMOTE_BIN} --version"

    @with_prompt_template
    @override
    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        model = self._resolve_model()
        env = self._env()

        pwd = await environment.exec(command="pwd")
        cwd = (pwd.stdout or "/app").strip() or "/app"

        await environment.exec(command=f"mkdir -p {_AGENT_LOG}", timeout_sec=30)

        message = instruction + _RULES
        think = f"--thinking-level {shlex.quote(self._thinking_level)} " if self._thinking_level else ""
        print_cmd = (
            f"{_REMOTE_BIN} __print -m {shlex.quote(message)} "
            f"--agent {_AID} -y --cwd {shlex.quote(cwd)} "
            f"--output-format stream-json {think}"
            f"--timeout {self._timeout_sec}s "
            f"> {_PRINT_JSONL} 2> {_PRINT_ERR}"
        )
        try:
            await environment.exec(
                command=print_cmd, env=env, timeout_sec=self._timeout_sec
            )
        finally:
            # Snapshot task fs + capture dogfood tree (runs even on timeout cancel).
            await environment.exec(
                command=(
                    "{ echo '== pwd =='; pwd; echo '== find /app maxdepth3 =='; "
                    "find /app -maxdepth 3 2>/dev/null; } "
                    f"> {_AGENT_LOG}/POSTRUN_ls.txt 2>&1; true"
                ),
                timeout_sec=60,
            )
            await environment.exec(command=_CAPTURE_DOGFOOD_TMPL, env=env, timeout_sec=240)
