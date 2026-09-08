"""Apply explicit K3 metadata through mcode's normal YAML configuration."""
import json
import shlex
from pathlib import Path

from frontierharness_mcode import OfflineMCode


class ConfiguredMCode(OfflineMCode):
    """Keep Harbor's execution unchanged and extend only model configuration."""

    def __init__(self, *args, model_profile, **kwargs):
        self._model_profile = json.loads(Path(model_profile).read_text())
        allowed = {'name', 'attachment', 'reasoning', 'tool_call', 'temperature',
                   'modalities', 'limit', 'thinking', 'configuration_source'}
        if set(self._model_profile) - allowed:
            raise ValueError('Only model metadata may be configured here')
        super().__init__(*args, **kwargs)
        if self.model_name != 'openai/kimi-k3' or self._version != '0.3.2':
            raise ValueError('This profile was validated only for K3 and mcode 0.3.2')
        if self._model_profile['limit'] != {
            'context': self._context_window, 'output': self._max_output_tokens
        }:
            raise ValueError('Harbor limits and model profile must agree')

    def populate_context_post_run(self, context):
        super().populate_context_post_run(context)
        if context.n_input_tokens is not None:
            return
        output = self.logs_dir / self._OUTPUT_FILENAME
        if not output.exists():
            return
        usage = None
        for line in output.read_text().splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get('type') == 'exec.completed':
                usage = event.get('result', {}).get('usage')
        if not isinstance(usage, dict):
            return
        keys = ('inputTokens', 'cacheReadTokens', 'outputTokens')
        if not all(isinstance(usage.get(k), int) and usage[k] >= 0 for k in keys):
            return
        context.n_input_tokens = usage['inputTokens'] + usage['cacheReadTokens']
        context.n_cache_tokens = usage['cacheReadTokens']
        context.n_output_tokens = usage['outputTokens']
        context.metadata = {**(context.metadata or {}), 'mcode_usage': usage}

    def _build_model_limits_command(self, provider_key, requested_provider, model_id):
        limits = super()._build_model_limits_command(provider_key, requested_provider, model_id)
        # A JSON object is also a valid YAML value. Replace only this model's
        # generated defaults; retain provider credentials and the rest of config.
        code = r'''
const fs = require('node:fs');
const [file, provider, model, profile] = process.argv.slice(1);
const lines = fs.readFileSync(file, 'utf8').split('\n');
const custom = lines.indexOf('custom_provider:');
if (custom < 0) throw new Error('Missing custom provider configuration');
let start = -1, providerFound = false;
for (let i = custom + 1; i < lines.length; i++) {
  if (lines[i] && !lines[i].startsWith(' ')) break;
  if (/^  \S/.test(lines[i])) providerFound = lines[i] === `  ${provider}:`;
  if (providerFound && lines[i] === `      ${model}:`) {
    if (start >= 0) throw new Error('Ambiguous model configuration');
    start = i;
  }
}
if (start < 0) throw new Error('Unsupported mcode model configuration layout');
let end = start + 1;
while (end < lines.length && (!lines[end].trim() || /^ {7,}\S/.test(lines[end]))) end++;
const value = JSON.stringify(JSON.parse(profile));
lines.splice(start, end - start, `      ${model}: ${value}`);
fs.writeFileSync(`${file}.tmp`, lines.join('\n'));
fs.renameSync(`${file}.tmp`, file);
'''
        args = [str(Path(self._DATA_DIR) / 'config.yaml'), provider_key, model_id,
                json.dumps(self._model_profile, separators=(',', ':'))]
        apply = 'node -e ' + shlex.quote(code) + ' ' + shlex.join(args)
        return limits + ' && ' + apply
