"""Harbor / Pier InstalledAgent adapter for AiWork (agentix `dtcoder` binary) — PIER variant (DeepSWE, air-gapped).

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

from pier.agents.installed.base import BaseInstalledAgent, with_prompt_template
from pier.environments.base import BaseEnvironment
from pier.models.agent.context import AgentContext
from pier.models.agent.network import NetworkAllowlist
from pier.models.agent.install import AgentInstallSpec, InstallStep

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

        # NOTE: Pier air-gaps the task env behind a squid proxy that allowlists by
        # DOMAIN (network_allowlist below). dtcoder reaches the internal gateway via the container's
        # HTTP(S)_PROXY env; we must NOT pin MaaS IPs into /etc/hosts (that would dial
        # the IP directly and bypass the proxy on the internal net -> PROVIDER_NETWORK_ERROR).

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

    def network_allowlist(self) -> NetworkAllowlist:
        # DeepSWE tasks are allow_internet=false; Pier air-gaps the task env but
        # allowlists the agent's own LLM egress. dtcoder must reach the internal gateway.
        from urllib.parse import urlparse as _u
        host = _u(self._provider_url).hostname or "<internal-gateway-host>"
        return NetworkAllowlist(domains=[host])

    def install_spec(self) -> AgentInstallSpec:
        # agent_name deliberately != name() so Pier's setup() does NOT treat the
        # agent as preinstalled and DOES call our imperative install() (which
        # uploads the dtcoder binary + runs dtcoder init). The noop step only
        # satisfies the non-empty AgentInstallSpec requirement.
        return AgentInstallSpec(
            agent_name=f"{self.name()}-declared-noop",
            steps=[InstallStep(run="true", user="root")],
            verification_command=f"{_REMOTE_BIN} --version",
        )

    def populate_context_post_run(self, context: AgentContext) -> None:
        try:
            import json as _json
            pj = self.logs_dir / "print.jsonl"
            if not pj.is_file():
                return
            prof = None; flat = None
            for line in pj.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    o = _json.loads(line)
                except Exception:
                    continue
                ev = o.get("event") or {}
                nm = ev.get("name") if isinstance(ev, dict) else ev
                d = o.get("data")
                if not isinstance(d, dict):
                    continue
                if nm == "stream.profiling" and d.get("summary"):
                    prof = (d.get("summary") or {}).get("total_token_usage") or {}
                elif nm == "stream.usage" and "input_tokens" in d:
                    flat = d
            sm = prof or flat
            if sm:
                context.n_input_tokens = int(sm.get("input_tokens") or 0)
                context.n_cache_tokens = int(sm.get("cache_read_tokens") or 0)
                context.n_output_tokens = int(sm.get("output_tokens") or 0)
        except Exception:
            pass

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
            # exec_as_agent routes through Pier's agent_process_env, which merges the
            # squid HTTP(S)_PROXY for THIS agent exec only (agent-phase-scoped; the
            # verifier/task never sees it). That is how dtcoder reaches the internal gateway under
            # the air-gapped DeepSWE task without opening the task container's network.
            await self.exec_as_agent(
                environment, command=print_cmd, env=env, timeout_sec=self._timeout_sec
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
