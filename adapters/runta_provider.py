"""Attach an existing managed model provider to each Harbor Runta runtime.

Each runtime also gets a loopback LiteLLM proxy on PROXY_URL. Harnesses call it with
any model name over Chat Completions, Anthropic Messages, Responses or Gemini; it sends
every request to the provider's model with the study's reasoning effort and output cap.
"""

import asyncio
import json
import os
import random
import shlex
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from harbor.environments.runta import RuntaEnvironment

ATTEMPTS = 5
_providers: dict[str, asyncio.Future] = {}

PROXY_URL = 'http://127.0.0.1:4011'
PROXY_HOME = '/opt/fhe-proxy'
UV_VERSION = '0.13.5'
LITELLM = 'litellm[proxy]==1.106.2'
# Runs inside LiteLLM, after each request is translated to Chat Completions. Requests
# under 1,024 output tokens are side calls (session titles) and keep their budget.
PROXY_HOOK = '''from litellm.integrations.custom_logger import CustomLogger

MAX_OUTPUT_TOKENS, SIDE_CALL_TOKENS = 131072, 1024


class StudySettings(CustomLogger):
    async def async_pre_call_deployment_hook(self, kwargs, call_type):
        if getattr(call_type, 'value', call_type) != 'acompletion':
            return None
        requested = kwargs.pop('max_completion_tokens', None) or kwargs.get('max_tokens')
        side_call = isinstance(requested, int) and requested < SIDE_CALL_TOKENS
        kwargs['max_tokens'] = requested if side_call else MAX_OUTPUT_TOKENS
        kwargs.pop('thinking', None)
        kwargs['reasoning_effort'] = 'max'
        return kwargs


hook = StudySettings()
'''
# Agents stop their own work with `pkill -f python`; the proxy's command line avoids that word.
PROXY_START = f'''set -eu
command -v curl >/dev/null || {{ apt-get update && apt-get install -y curl ca-certificates; }}
export UV_PYTHON_INSTALL_DIR={PROXY_HOME}/python UV_PYTHON_PREFERENCE=only-managed
curl -LsSf https://astral.sh/uv/{UV_VERSION}/install.sh | env UV_UNMANAGED_INSTALL={PROXY_HOME} sh
{PROXY_HOME}/uv venv --clear --python 3.12 {PROXY_HOME}/venv
{PROXY_HOME}/uv pip install --link-mode copy --python {PROXY_HOME}/venv/bin/python {shlex.quote(LITELLM)}
ln -sf python {PROXY_HOME}/venv/bin/model-proxy
mkdir -p /logs/agent
cd {PROXY_HOME}
nohup venv/bin/model-proxy venv/bin/litellm --config config.yaml --host 127.0.0.1 --port {urlsplit(PROXY_URL).port} \\
  >/logs/agent/model-proxy.log 2>&1 </dev/null &
for attempt in $(seq 120); do
  curl -fs {PROXY_URL}/health/liveliness >/dev/null && exit 0
  sleep 1
done
exit 1
'''


async def _runta(*args: str) -> str:
    # The CLI fails transiently, often with empty stderr, when hundreds of
    # trials start at once, so retry and report both streams.
    for attempt in range(ATTEMPTS):
        process = await asyncio.create_subprocess_exec(
            'runta', *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if not process.returncode:
            return stdout.decode()
        if attempt + 1 < ATTEMPTS:
            await asyncio.sleep(2**attempt + random.random() * 2**attempt)
    detail = ' '.join(s.decode().strip() for s in (stderr, stdout) if s.strip())
    raise RuntimeError(f'Runta provider setup failed (exit {process.returncode}): {detail}')


async def _describe(provider: str) -> dict:
    """Provider metadata, fetched once per event loop and shared by concurrent trials."""
    future = _providers.get(provider)
    if (
        future is None
        or future.get_loop() is not asyncio.get_running_loop()
        or (future.done() and (future.cancelled() or future.exception()))
    ):
        future = _providers[provider] = asyncio.ensure_future(_runta('model-provider', 'describe', provider, '--json'))
    return json.loads(await asyncio.shield(future))['details']


class ManagedProviderEnvironment(RuntaEnvironment):
    def __init__(self, *args, expected_base_url: str, upstream_model: str, **kwargs):
        self._model_provider = os.environ['RUNTA_MODEL_PROVIDER']
        self._expected_base_url = expected_base_url
        self._upstream_model = upstream_model
        super().__init__(*args, **kwargs)

    @property
    def separate_verifier(self) -> bool:
        """Harbor builds a task's separate verifier from the job's environment config.

        It only runs tests, so it needs no model route, and some (batched-eval-parity)
        have no internet for the provider bridges to install from.
        """
        return '__verifier' in self.session_id

    async def start(self, force_build: bool) -> None:
        if self.separate_verifier:
            return await super().start(force_build)
        metadata = await _describe(self._model_provider)
        if metadata['base_url'] != self._expected_base_url:
            raise ValueError("Managed provider endpoint differs from the job's endpoint")
        endpoint = urlsplit(metadata['base_url'])
        if endpoint.scheme != 'https' or not endpoint.hostname:
            raise ValueError('Managed provider must use an HTTPS endpoint')
        await super().start(force_build)
        await _runta(
            'secret',
            'rule',
            'set',
            self._runtime_name(),
            '--secret',
            metadata['secret_id'],
            '--host',
            endpoint.hostname,
            '--path',
            endpoint.path.rstrip('/') + '/*',
            '--header',
            metadata['header_name'],
            '--template',
            metadata['value_template'],
        )
        await self._start_proxy(metadata['base_url'])

    async def _start_proxy(self, base_url: str) -> None:
        config = {
            'model_list': [
                {
                    'model_name': '*',
                    'litellm_params': {
                        'model': f'openai/{self._upstream_model}',
                        'api_base': base_url,
                        'api_key': 'os.environ/PROVIDER_STUB_KEY',
                        'use_chat_completions_api': True,
                    },
                }
            ],
            'litellm_settings': {'drop_params': True, 'callbacks': 'study_settings.hook'},
            # The proxy listens on the runtime's loopback only.
            'general_settings': {'dangerously_permit_weak_or_unset_master_key': True},
        }
        await self.exec(f'mkdir -p {PROXY_HOME}', user='root')
        with tempfile.TemporaryDirectory() as tmp:
            # JSON is valid YAML.
            for name, content in {'config.yaml': json.dumps(config), 'study_settings.py': PROXY_HOOK}.items():
                (Path(tmp) / name).write_text(content)
                await self.upload_file(Path(tmp) / name, f'{PROXY_HOME}/{name}')
        result = await self.exec(
            PROXY_START, env={'PROVIDER_STUB_KEY': os.environ['PROVIDER_STUB_KEY']}, user='root'
        )
        if result.return_code:
            raise RuntimeError(f'Model proxy failed to start: {result.stdout or ""}{result.stderr or ""}')
