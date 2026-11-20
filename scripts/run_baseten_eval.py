"""Run the Baseten suite: one Harbor job per model.

suites/baseten-eval.json is a Harbor job config with three additions, resolved here
into the plain config each job runs:

- `{model_id}` (the Baseten model ID) and `{alias}` (the slash-free name harnesses
  request) are filled in per model from MODELS.
- `agent_defaults` is merged into every agent; an agent's own `env` and `kwargs` keys win.
- A list item that is exactly "@name" in an agent's kwargs is replaced by the items of `snippets[name]`.

An agent whose `uploads` source is missing on this host is left out with a warning.
`--tasks` and `--attempts 1` narrow a job to a smoke test, and `--dry-run` validates
each job with `harbor run --dry-run` without starting it.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / 'suites/baseten-eval.json'
JOBS = ROOT / 'jobs'
HARBOR = Path(sys.executable).with_name('harbor')
MODELS = {
    'glm-5.3': 'zai-org/GLM-5.3',
    'glm-5.3-flash': 'zai-org/GLM-5.3-Flash',
    'deepseek-v4.1-flash-1017': 'deepseek-ai/DeepSeek-V4.1-Flash-1017',
    'muse-spark-open': 'meta-models/muse-spark-open',
    'kimi-k3': 'moonshotai/Kimi-K3',
    'kimi-k3.1-pro': 'moonshotai/Kimi-K3.1-Pro',
}
DEFAULT_MODELS = ('glm-5.3', 'glm-5.3-flash', 'deepseek-v4.1-flash-1017', 'muse-spark-open', 'kimi-k3')


def expand(value, snippets):
    if isinstance(value, dict):
        return {key: expand(item, snippets) for key, item in value.items()}
    if isinstance(value, list):
        items = []
        for item in value:
            if isinstance(item, str) and re.fullmatch(r'@[\w-]+', item):
                items.extend(expand(snippets[item[1:]], snippets))
            else:
                items.append(expand(item, snippets))
        return items
    return value


def agent_config(defaults, agent, snippets):
    merged = {**defaults, **agent}
    for key in ('env', 'kwargs'):
        merged[key] = {**defaults.get(key, {}), **agent.get(key, {})}
    merged['kwargs'] = expand(merged['kwargs'], snippets)
    uploads = merged['kwargs'].get('uploads', {})
    missing = [source for source in uploads if not (ROOT / source).is_file()]
    if missing:
        name = merged['kwargs'].get('harness', merged.get('name'))
        print(f'warning: leaving out {name}; missing {", ".join(missing)}', file=sys.stderr)
        return None
    if uploads:
        merged['kwargs']['uploads'] = {str(ROOT / source): target for source, target in uploads.items()}
    return merged


def job_config(alias, job, attempts=None, tasks=()):
    text = SUITE.read_text().replace('{model_id}', MODELS[alias]).replace('{alias}', alias)
    config = json.loads(text)
    defaults, snippets = config.pop('agent_defaults'), config.pop('snippets')
    config['agents'] = [a for a in (agent_config(defaults, a, snippets) for a in config['agents']) if a]
    config['job_name'] = job
    if attempts:
        config['n_attempts'] = attempts
    if tasks:
        for dataset in config['datasets']:
            dataset['task_names'] = list(tasks)
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', nargs='+', choices=tuple(MODELS), default=DEFAULT_MODELS)
    parser.add_argument('--attempts', type=int, help='Attempts per harness and task (default: the suite, 4)')
    parser.add_argument('--tasks', nargs='+', default=(), help='Run only these tasks (glob patterns), e.g. "*/fix-git"')
    parser.add_argument('--job-prefix')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    prefix = args.job_prefix or f'{SUITE.stem}-' + datetime.now().strftime('%Y%m%d-%H%M%S')
    JOBS.mkdir(exist_ok=True)
    code = 0
    for alias in dict.fromkeys(args.model):
        job = f'{prefix}-{alias}'
        config = job_config(alias, job, args.attempts, args.tasks)
        path = JOBS / f'{job}.config.json'
        path.write_text(json.dumps(config, indent=2) + '\n')
        print(f'{job}: {MODELS[alias]}, {len(config["agents"])} harnesses x {config["n_attempts"]} attempts', flush=True)
        command = [str(HARBOR), 'run', '-c', str(path), '--jobs-dir', str(JOBS), *(['--dry-run'] if args.dry_run else [])]
        code = subprocess.call(command, cwd=ROOT) or code
    return code


if __name__ == '__main__':
    raise SystemExit(main())
