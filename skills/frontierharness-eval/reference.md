# Reference

Command reference, runner templates, and troubleshooting for `frontierharness-eval`.

## Runta CLI commands used

| Purpose | Command |
| --- | --- |
| Create a clean runtime | `runta run --name demo --cpus 4 --memory 8192 --disk-size-gib 100` |
| Run a command inside it | `runta exec demo -- sh -lc 'harbor --version'` |
| Copy files in or out | `runta cp local.txt demo:/work/` · `runta cp demo:/work/jobs ./jobs` |
| Store a provider key | `runta secret set OPENAI_API_KEY --value-env OPENAI_API_KEY` |
| Restrict network | `runta egress set demo --mode allowlist --allow api.fireworks.ai` |
| Freeze a golden checkpoint | `runta checkpoint create demo fh-golden-v1` |
| Restore a fresh runtime | `runta checkpoint restore fh-golden-v1 fh-trial-01` |
| List checkpoints | `runta checkpoint ls` |
| Inspect or clean up | `runta inspect demo` · `runta rm demo` |

`runta run` requires both `--cpus` and `--memory`. `--disk-size-gib` defaults to 16,
which is too small for the eval environment, so pass 100. Restoring a checkpoint always
creates a new runtime with the checkpoint's capacity; it never mutates the checkpoint. Full docs: <https://runta.com/docs/>.

Use `--` before the remote command in `runta exec` whenever arguments could be parsed as
CLI options, and wrap multi-step commands in `sh -lc '...'`.

## Model and providers

The benchmark fixes the **model** at **Kimi K3**, matching `benchmark.json`
(`"model": "Kimi K3"`). Both scripts warn if the model is anything else. The
**provider** is a choice: the published baselines used Fireworks
(`"model_provider": "Fireworks"`), but the same weights from another provider give a
comparable pass rate. Select one with `--provider`; the presets live in
`scripts/providers.sh`.

| `--provider` | Model route | Credential | Egress host |
| --- | --- | --- | --- |
| `fireworks` (default) | `fireworks_ai/accounts/fireworks/models/kimi-k3` | `FIREWORKS_API_KEY` | `api.fireworks.ai` |
| `moonshot` | `moonshot/kimi-k3` | `MOONSHOT_API_KEY` | `api.moonshot.ai` |
| `openrouter` | `openrouter/moonshotai/kimi-k3` | `OPENROUTER_API_KEY` | `openrouter.ai` |
| `together` | `together_ai/moonshotai/Kimi-K3` | `TOGETHER_API_KEY` | `api.together.xyz` |
| `cursor` (only with `--harness cursor-cli`) | `kimi-k3`, Cursor's own model slug | `CURSOR_API_KEY` | `api2.cursor.sh` |
| `custom` | `--model` (required) | `--secret-name` (required) | set egress yourself |

`cursor` is the one preset that is not a provider in the same sense: Cursor's headless CLI
sends model calls through Cursor's backend to Cursor's inference partner for Kimi K3, so
it pairs only with the `cursor-cli` harness and lands with a provider caveat. Details,
egress hosts, and pricing: [cursor-cli.md](cursor-cli.md).

The provider prefix is the LiteLLM provider route, which is what Harbor, Pier, and
`mini-swe-agent` expect. A harness that calls the provider directly through an
OpenAI-compatible client wants the bare model id against that provider's base URL
instead: `accounts/fireworks/models/kimi-k3` at `https://api.fireworks.ai/inference/v1`,
`kimi-k3` at `https://api.moonshot.ai/v1`, and so on. Moonshot's China platform is
`https://api.moonshot.cn/v1` with a separate key; keys are not interchangeable across
its regional platforms.

Use `custom` for a gateway, a regional endpoint, or a provider not listed here, and keep
the model id recognisably Kimi K3 or the scripts will warn:

```bash
--provider custom \
  --model openai/kimi-k3 \
  --secret-name MY_GATEWAY_API_KEY
```

Whichever provider you pick, set egress to its host so trials stay air-gapped apart from
the model call:

```bash
runta egress set fh-build --mode allowlist --allow api.moonshot.ai
```

### Cost comparability

Pass rate survives a provider swap because the model is identical. Cost only survives if
the token prices do. Moonshot's list price is $3.00 per million input tokens, $0.30 per
million cached input tokens, and $15.00 per million output tokens, and Fireworks
standard serverless, OpenRouter, and Together all matched those three numbers at the
time of writing. Verify against the provider's own pricing page before comparing a cost
number, since these move; `build-report.mjs` flags any non-baseline provider as a caveat
rather than assuming parity.

Two Fireworks routers are traps: `kimi-k3-fast` and `kimi-k3-us` are the same weights at
a premium (+50% and +10%), which inflates every cost metric relative to the baselines.

Cached reads being 10x cheaper than fresh input is why cache hit rate moves cost so much
between harnesses, and why the published baselines reprice first-turn cache reads before
comparing. Providers also differ in cache *behaviour* — minimum prefix length and TTL —
so a provider swap can shift cache hit rate even at identical prices.

## Runner templates

`run-trials.sh` picks a template from the task id prefix. Override with `--cmd`.
Placeholders: `{task}`, `{suite}`, `{harness}`, `{model}`, `{jobs}`.

**Terminal-Bench through Harbor** (`terminal-bench/*`):

```
harbor run -d terminal-bench/terminal-bench@4.0.0 --task-id {task} -a {harness} -m {model} --jobs-dir {jobs}
```

**DeepSWE through Pier** (`datacurve/*`):

```
pier run -p /work/deep-swe/tasks/{task} --agent {harness} --model {model} --output-dir {jobs}
```

Verify the flag names against the installed versions before a full run — Harbor and Pier
both change CLI surface between releases:

```bash
runta exec fh-build -- sh -lc 'harbor run --help | head -40'
runta exec fh-build -- sh -lc 'pier run --help | head -40'
```

Pier exists because Harbor blocks all outbound traffic on `allow_internet = false`
tasks, including the agent's own LLM calls. Pier adds per-agent network allowlists, so
the agent reaches its provider while the task environment stays isolated. That is why
DeepSWE tasks go through Pier rather than Harbor.

If a harness is not a built-in agent for either runner, register it as a custom agent in
the runner's agent registry inside `--install-script`, then pass its registered name as
`--harness`.

## Running Harbor with Runta as the environment provider

The skill's default topology runs Harbor and Pier *inside* one Runta runtime, which is
what makes a single golden checkpoint cover the whole stack. The alternative is to run
Harbor locally and let Runta provide a fresh runtime per trial:

```bash
uv pip install 'runta-sdk[harbor]'
harbor run -d terminal-bench-sample@2.0 -a oracle -l 1 \
  --environment-import-path runta_harbor.environment:RuntaEnvironment \
  --ek mode=auto
```

This parallelizes better, but Harbor controls runtime creation, so trials no longer
start from one shared golden checkpoint. Prefer it only for large sweeps where
throughput matters more than identical cold starts, and say so in the report.

Known limitations of the provider: `harbor run -e runta` is not registered yet, so the
import path is required; GPU, TPU, Windows, and mounted-resource tasks are unsupported;
storage overrides are accepted but not applied.

## Task metadata

Each `tasks/<task>/task.toml` in this repo carries the environment contract:

```toml
[metadata]
task_id = "anko-typed-variable-bindings"
repository_url = "https://github.com/mattn/anko"
base_commit_hash = "3f269a72ff69398b1250c584171f32d12c0d8085"
[agent]
network_mode = "no-network"
timeout_sec = 5400.0
[environment]
docker_image = "public.ecr.aws/..."
cpus = 2
memory_mb = 8192
```

Match `cpus`, `memory_mb`, and `timeout_sec` when running a task, otherwise results are
not comparable to the baseline. `provision-golden-checkpoint.sh --prepull-tasks tasks`
reads `docker_image` from these files to warm the image cache before the checkpoint.

## Trial record contract

`run-trials.sh` writes one `trial.json` per task. `normalize-results.mjs` reads only
these fields, so any custom runner can produce them directly:

```json
{
  "id": "terminal-bench/regex-log",
  "title": "regex-log",
  "suite": "terminal-bench",
  "status": "success",
  "success": true,
  "duration_seconds": 269,
  "cost_first_cold_usd": 0.0561,
  "turns": 3,
  "cache_hit_rate_normalized": 0.521,
  "exit_code": 0,
  "runtime": "fh-2026-09-02-terminal-bench-regex-log",
  "checkpoint": "fh-golden-myharness-v1"
}
```

`status` is one of `success`, `failure`, `timeout`, or `infra_invalid`. Only
`infra_invalid` is excluded from scoring.

Reward extraction scans the collected job directory for the first non-null
`resolved`, `is_resolved`, `reward`, or `passed` field. If a runner reports success
differently, the extracted value will be wrong — spot-check the first trial:

```bash
jq . runs/<run-id>/trials/<task>/trial.json
find runs/<run-id>/trials/<task>/jobs -name '*.json' | head
```

## Troubleshooting

**`No module named 'runta_harbor'`** — `harbor` is running from a Python environment
without `runta-sdk[harbor]`, usually a global `uv tool` install at `~/.local/bin/harbor`.
Use `uvx --with "runta-sdk[harbor]" harbor run ...`.

**`RESOURCE_EXHAUSTED` on create or restore** — the tenant CPU or memory limit is
reached. Delete leftover trial runtimes: `runta ps -a` then `runta rm <name>`. A crashed
`run-trials.sh` can leave runtimes behind.

**Agent cannot reach the model provider** — the task is air-gapped. Confirm the runtime
egress policy allows the provider host and that the key is a stub inside the runtime:

```bash
runta egress describe fh-build
runta exec fh-build -- sh -lc 'test "$FIREWORKS_API_KEY" = runta-secret-stub && echo stubbed'
```

**Every task fails identically at turn zero** — almost always harness configuration, not
task difficulty. Restore the checkpoint once and run the harness by hand before spending
a full sweep:

```bash
runta checkpoint restore fh-golden-myharness-v1 fh-debug
runta exec fh-debug -- sh -lc 'cd /work && <runner command with one task>'
```

**Costs are null in the report** — the runner did not emit usage in its job output.
Either enable usage reporting in the harness or record cost from the provider dashboard
and patch `cost_first_cold_usd` into each `trial.json` before normalizing.
