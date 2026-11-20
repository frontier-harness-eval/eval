"""Run the pinned DeepSeek Harness CLI in a Linux task container."""
import asyncio
import json
import os
from pathlib import Path
import shlex
import tempfile

from .bundle import HERE, prepare_bundle

VERSION = json.loads((HERE / "package.json").read_text())["dependencies"]["@deepseek-ai/dsh"]
CLI = "/opt/fh-dsh/node_modules/@deepseek-ai/dsh/lib/bin.js"

PRESETS = {"dsh": None, "dsh-standard": "standard", "dsh-ptc": "code", "dsh-creator": "cordis"}


class DshRuntime:
    """Shared task-container protocol for Harbor and Pier."""

    def __init__(
        self, *args, base_url, secret_name, platform, harness="dsh",
        api="openai-responses", web_search_max_keywords=None, **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.harness = harness
        self.preset = PRESETS[harness]
        self.api = api
        self.base_url = base_url.rstrip("/")
        self.secret_name = secret_name
        self.platform = platform
        self.web_search_max_keywords = web_search_max_keywords

    @staticmethod
    def name():
        return "dsh"

    def to_agent_info(self):
        info = super().to_agent_info()
        return info.model_copy(update={"name": self.harness})

    def version(self):
        return VERSION

    async def setup(self, environment):
        archive = await asyncio.to_thread(prepare_bundle, self.platform)
        await environment.upload_file(archive, "/tmp/fh-dsh.tgz")
        await environment.upload_file(HERE / "responses.cjs", "/tmp/fh-dsh-responses.cjs")
        if self.preset:
            await environment.upload_file(HERE / "preset-runner.mjs", "/tmp/fh-dsh-preset.mjs")
        result = await environment.exec(
            f"mkdir -p /opt/fh-dsh && tar xzf /tmp/fh-dsh.tgz -C /opt/fh-dsh && "
            f"rm /tmp/fh-dsh.tgz && /opt/fh-dsh/node {CLI} --version", user="root",
        )
        if result.return_code or VERSION not in (result.stdout or ""):
            raise RuntimeError(f"Failed to install DSH {VERSION}: {result.stderr}")

    def route(self, instruction):
        model_id = self.model_name
        if self.api == "openai-completions":
            model_id = model_id.removeprefix("fireworks_ai/")
        model = {"id": model_id, "name": model_id, "contextWindow": 131072, "maxTokens": 32768}
        if model_id == "accounts/fireworks/models/kimi-k3" and self.api == "openai-completions":
            model.update(contextWindow=1048576, input=["text", "image"])
        provider = {"api": self.api, "baseURL": self.base_url,
                    "apiKeyEnv": "MODEL_GATEWAY_KEY", "models": [model]}
        rows = [
            {"id": "agent-default-model", "config": {"provider": "evaluation", "model": model_id}},
            {"id": "llm-pi-ai", "config": {"providers": {"evaluation": provider}}},
            {"id": "session-persistence-jsonl", "config": {"root": "/tmp/fh-dsh-home/sessions", "compression": "none"}},
            {"id": "tools", "config": {"mode": "native"}},
        ]

        if self.preset:
            rows.extend([
                {"id": "session-title-llm", "disabled": True},
                {"insert": [{"id": "fh-preset-runner", "name": "/tmp/fh-dsh-preset.mjs",
                             "config": {"preset": self.preset, "instruction": instruction}}]},
            ])
        return rows

    def inference_env(self, environment, env):
        return env

    async def run(self, instruction, environment, context):
        # The preload consumes the credential before DSH launches any tool processes.
        with tempfile.TemporaryDirectory() as staging:
            route = Path(staging) / "route.yml"
            route.write_text(json.dumps(self.route(instruction)))
            await environment.upload_file(route, "/tmp/fh-dsh-route.yml")
            key = Path(staging) / "key"
            key.write_text(os.environ[self.secret_name])
            key.chmod(0o600)
            await environment.upload_file(key, "/tmp/.fh-dsh-key")
            if environment.default_user is not None:
                result = await environment.exec(
                    f"chown {shlex.quote(str(environment.default_user))} /tmp/.fh-dsh-key", user="root",
                )
                if result.return_code:
                    raise RuntimeError("Cannot set DSH credential file ownership")
            if self.preset:
                args = "--profile web --patch /tmp/fh-dsh-route.yml --no-open --host 127.0.0.1 --port 0"
            else:
                args = "--profile headless --patch /tmp/fh-dsh-route.yml -- " + shlex.quote(instruction)
            run = f"""
set -eu
export PATH=/opt/fh-dsh:$PATH
mkdir -p "$DSH_HOME" /logs/agent
rc=0
/opt/fh-dsh/node --require /tmp/fh-dsh-responses.cjs {CLI} {args} > /logs/agent/dsh.stdout 2>/logs/agent/dsh.stderr || rc=$?
find "$DSH_HOME" -type f -name session.jsonl -exec cat {{}} + > /logs/agent/dsh-session.jsonl
exit "$rc"
"""
            suffix = "/chat/completions" if self.api == "openai-completions" else "/responses"
            env = {
                "MODEL_GATEWAY_KEY": "local-transport", "FH_DSH_RESPONSES_URL": self.base_url + suffix,
                "FH_DSH_WEB_SEARCH_MAX_KEYWORDS": str(self.web_search_max_keywords or ""),
                "DSH_HOME": "/tmp/fh-dsh-home", "DSH_TELEMETRY_DISABLED": "1", "DSH_TELEMETRY_MODE": "DISABLED", "DSH_TOOLS_MODE": "native",
            }
            if self.preset:
                # Benchmark task containers are unattended. The Web preset's
                # default workspace-write policy queues shell approval in the UI.
                env["DSH_PERMISSION_MODE"] = "danger-full-access"
            result = await environment.exec(command=run, env=self.inference_env(environment, env))
            session = Path(staging) / "session.jsonl"
            await environment.download_file("/logs/agent/dsh-session.jsonl", session)
            fresh = cached = output = 0
            with session.open() as events:
                for line in events:
                    event = json.loads(line)
                    if event.get("type") == "assistant/message":
                        usage = event.get("data", {}).get("usage") or {}
                        fresh += usage.get("inputTokens") or 0
                        cached += usage.get("cacheReadTokens") or 0
                        output += usage.get("outputTokens") or 0
            if fresh or cached or output:
                context.n_input_tokens = fresh + cached
                context.n_cache_tokens = cached
                context.n_output_tokens = output
        if result.return_code:
            raise self.exit_error(f"DSH exited {result.return_code}, see dsh.stderr")
