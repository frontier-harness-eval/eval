"""Harbor adapter for the official DeepSeek Harness headless CLI."""
import asyncio
import json
import os
from pathlib import Path
import shlex
import tempfile

from harbor.agents.base import BaseAgent
from harbor.agents.installed.base import NonZeroAgentExitCodeError

from .bundle import HERE, prepare_bundle

VERSION = json.loads((HERE / "package.json").read_text())["dependencies"]["@deepseek-ai/dsh"]
CLI = "/opt/fh-dsh/node_modules/@deepseek-ai/dsh/lib/bin.js"


class DeepSeekHarness(BaseAgent):
    def __init__(self, *args, base_url, secret_name, platform, web_search_max_keywords=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.base_url = base_url.rstrip("/")
        self.secret_name = secret_name
        self.platform = platform
        self.web_search_max_keywords = web_search_max_keywords

    @staticmethod
    def name():
        return "dsh"

    def version(self):
        return VERSION

    async def setup(self, environment):
        archive = await asyncio.to_thread(prepare_bundle, self.platform)
        await environment.upload_file(archive, "/tmp/fh-dsh.tgz")
        await environment.upload_file(HERE / "responses.cjs", "/tmp/fh-dsh-responses.cjs")
        result = await environment.exec(
            f"mkdir -p /opt/fh-dsh && tar xzf /tmp/fh-dsh.tgz -C /opt/fh-dsh && "
            f"rm /tmp/fh-dsh.tgz && /opt/fh-dsh/node {CLI} --version", user="root",
        )
        if result.return_code or VERSION not in (result.stdout or ""):
            raise RuntimeError(f"Failed to install DSH {VERSION}: {result.stderr}")

    def route(self):
        model = {"id": self.model_name, "name": self.model_name, "contextWindow": 131072, "maxTokens": 32768}
        provider = {"api": "openai-responses", "baseURL": self.base_url,
                    "apiKeyEnv": "MODEL_GATEWAY_KEY", "models": [model]}
        return [
            {"id": "agent-default-model", "config": {"provider": "evaluation", "model": self.model_name}},
            {"id": "llm-pi-ai", "config": {"providers": {"evaluation": provider}}},
            {"id": "session-persistence-jsonl", "config": {"root": "/tmp/fh-dsh-home/sessions", "compression": "none"}},
            {"id": "tools", "config": {"mode": "native"}},
        ]

    async def run(self, instruction, environment, context):
        # The preload consumes the credential before DSH launches any tool processes.
        with tempfile.TemporaryDirectory() as staging:
            route = Path(staging) / "route.yml"
            route.write_text(json.dumps(self.route()))
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
            run = f"""
set -eu
export PATH=/opt/fh-dsh:$PATH
mkdir -p "$DSH_HOME" /logs/agent
rc=0
/opt/fh-dsh/node --require /tmp/fh-dsh-responses.cjs {CLI} --profile headless \\
  --patch /tmp/fh-dsh-route.yml -- {shlex.quote(instruction)} > /logs/agent/dsh.stdout 2>/logs/agent/dsh.stderr || rc=$?
find "$DSH_HOME" -type f -name session.jsonl -exec cat {{}} + > /logs/agent/dsh-session.jsonl
exit "$rc"
"""
            result = await environment.exec(command=run, env={
                "MODEL_GATEWAY_KEY": "local-transport", "FH_DSH_RESPONSES_URL": self.base_url + "/responses",
                "FH_DSH_WEB_SEARCH_MAX_KEYWORDS": str(self.web_search_max_keywords or ""),
                "DSH_HOME": "/tmp/fh-dsh-home", "DSH_TELEMETRY_MODE": "DISABLED", "DSH_TOOLS_MODE": "native",
            })
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
            raise NonZeroAgentExitCodeError(f"DSH exited {result.return_code}, see dsh.stderr")
