# MiniMax Code 0.3.2 with Kimi K3

This profile publishes the agent/runner adapters used by the completed candidate in
[#13](https://github.com/frontier-harness-eval/eval/pull/13). It replaces the 0.2.7,
all-Harbor proposal in [#2](https://github.com/frontier-harness-eval/eval/pull/2):
**Terminal-Bench uses Harbor 0.22.0; DeepSWE uses Pier 0.3.1.**
Follow the [official skill](../../SKILL.md) for checkpoint creation, fresh restores,
first-valid-attempt selection and reporting. No official script or task is changed here.

## Adaptation boundary

- `frontierharness_mcode.py` subclasses Harbor's built-in MCode agent only to install
  the archived Node/mcode bundle without task-time package downloads.
- `mcode_kimi_profile.py` adds K3 model metadata through mcode's normal configuration
  and reads its final usage event when Harbor has no per-message usage.
- `pier_mcode.py` and `pier-proxy.cjs` run the same agent through Pier's public
  interface and authenticated proxy, allowlisted only for `api.moonshot.cn`. The Node
  preload applies only to the mcode command; tool subprocesses can inherit Pier's
  HTTP(S) proxy environment. This profile does not change that native behavior.
- `pier_environment.py` preserves Pier's native log mounts when adding CA/session mounts.
- `run_task.py` implements the official `--cmd` hook: select the suite runner, supply
  configuration and expose the native verifier reward for the official extractor.
  Native results remain intact; absent rewards and usage stay unknown.

Task instructions, images, verifiers, native phase limits, resources and Harbor's mcode
execution logic are unchanged. The profile uses one native attempt and zero automatic
retries. It adds no task-specific prompt, extra task tool, answer retry or scoring rule.
Harbor's existing BYOK behavior disables login-backed web search. X-Ray and prompt
compression were disabled for the submitted run.

## Pins and K3 settings

| Component | Submitted run |
| --- | --- |
| Official eval code | `8f11b130c30bbf76ca1f3edeea70abc773bd8d2c` |
| MiniMax Code | Official npm release `@minimax-ai/code@0.3.2` |
| Node / Python | `22.23.2` Linux x86-64 / `3.12.3` |
| Harbor / Pier / Runta SDK | `0.22.0` / `0.3.1` / `0.2.0` |
| Pier client proxy dependency | `undici@8.10.2` |
| Terminal-Bench source | `laude-institute/terminal-bench-2@69671fbaac6d67a7ef0dfec016cc38a64ef7a77c` |
| DeepSWE source | `datacurve-ai/deep-swe@435ee89ec2f2e2289f33b0da4f992f0b7b7266b9` |

The npm release publishes no source repository or `gitHead`; the eval checkout commit
is not mcode's source commit. `requirements.txt` pins the runner packages. The archived
checkpoint manifest records the full Python dependency list, and the archived mcode
runtime contains its installed npm dependencies. A new package resolution is not
necessarily identical to the archived environment.

`kimi-k3-model-settings.json` supplies reasoning/tool support, **thinking=max**,
**1,048,576** context tokens and **131,072** output tokens. Sampling uses mcode/provider
defaults; no temperature override or separate reasoning-token budget is added.
The model route is `openai/kimi-k3`, with `openai-completions` and
`https://api.moonshot.cn/v1`. Configuration contains only `runta-secret-stub`; Runta
injects the actual key on egress. Other provider routes are outside this profile's scope.

## Reproduction inputs

The [review bundle](https://drive.google.com/file/d/123TBFZFFthLGoUtxW62J3N8SbEdw-lsC/view)
contains the 30 raw trial archives, results CSV, original preparation/execution scripts,
frozen official code and checkpoint references. Relevant paths inside the bundle:

| Path | Purpose |
| --- | --- |
| `scripts/used/` | Actual preparation, execution and collection code |
| `scripts/official-frozen/` | Official skill/scripts used for this run |
| `checkpoint/RESTORE.md` | Checkpoint access and rebuild context |
| `checkpoint/dependency-inputs/mcode-runtime.tar.gz` | Installed Node + mcode 0.3.2 |
| `checkpoint/dependency-inputs/undici-8.10.2.tgz` | Pier proxy dependency |
| `checkpoint/rebuild-records/manifest.json` | Full dependency and runtime metadata |

For the official skill's installation phase, stage these adapters and dependencies
at the following paths in the clean runtime. The task directories must be the unchanged
sources at the pins above, selecting the official 21 Terminal-Bench and 9 DeepSWE tasks:

```text
/work/frontierharness/
  venv/                         # requirements.txt, Python 3.12
  terminal-bench/<task>/         # native task sources
  deep-swe/tasks/<task>/         # native task sources
  mcode-runtime.tar.gz
  kimi-k3-model-settings.json
  official/                     # the six .py/.cjs adapters in this profile
    undici-8.10.2.tgz
```

Use the original preparation scripts in the bundle as the record of the executed
procedure. They pre-pull native task images and cache Pier's unchanged proxy Dockerfile;
formal tasks must not run before the golden checkpoint. Keep 4 vCPU, 8192 MiB memory
and 100 GiB disk, and validate each native runner on a separate sample restore.
A checkpoint reference is not a VM export: another account needs access from Runta
or must rebuild from these inputs.

The submitted environment also used upstream #11's dependency-download allowlist and
scoped system-runc repair, plus the pinned DeepSWE source because the `v1.1` Git ref was
unavailable. Those infrastructure changes and the original detached execution are in
the bundle, **not reimplemented by this profile**. Unpatched main at the pin above
still has these infrastructure limitations; adding the agent alone does not fix them.
Before a new run, use the applicable upstream fixes and confirm the stored egress
policy on restores. Terminal-Bench package downloads are allowed; Pier's agent proxy
is limited to `api.moonshot.cn`. Historical baseline network parity is not established.

## Official runner hook and results

Once the checkpoint and infrastructure prerequisites above are ready, the integration
command for the official `run-trials.sh` is below. Use a new output directory; these
commands are for a new run, not for overwriting the archived candidate in #13.

Before reporting, check the native verifier records: the official normalizer counts
timeouts as completed non-passes and does not retain a separate unscored count. For the
submitted run, its 30 completed attempts mean **27 scored and 3 unscored**, with 23
passes. Keep that distinction alongside `candidate.json`; do not describe all 30 as
verifier-scored or the three missing scores as verifier failures. Review #13 against
the archived per-task summary and native records, rather than replacing its artifacts.

```bash
FH=skills/frontierharness-eval/scripts
bash "$FH/run-trials.sh" \
  --checkpoint YOUR_READY_CHECKPOINT --harness mcode \
  --provider custom --model openai/kimi-k3 \
  --secret-name OPENAI_API_KEY --secret-host api.moonshot.cn \
  --run-id frontierharness-mcode-kimi --out runs --timeout 5400 \
  --cmd 'env PYTHONPATH=/work/frontierharness/official PATH=/work/frontierharness/venv/bin:/usr/local/bin:/usr/bin:/bin /work/frontierharness/venv/bin/python /work/frontierharness/official/run_task.py --suite {suite} --task {task} --model {model} --jobs {jobs}'

node "$FH/normalize-results.mjs" --run runs/frontierharness-mcode-kimi --label 'MiniMax Code'
node "$FH/generate-chart.mjs" --run runs/frontierharness-mcode-kimi
node "$FH/build-report.mjs" --run runs/frontierharness-mcode-kimi
```

The normalizer requires `<run>/run.json`, not `run-config.json`. Keep each trial's
native `jobs/`, mcode JSONL, stderr, sessions and verifier files. In-flight requests can
lack returned usage when cancelled; this adapter does not invent a complete bill.

The official script's **outer 5400-second deadline** includes setup and verification;
it is distinct from native agent/verifier time limits. In the submitted run,
`arktype-json-schema-refs-dependencies`, `meriyah-explicit-resource-declarations` and
`python-statemachine-state-data-scoping` ended with native `CancelledError` before
verification. These are three unscored outer timeouts, not verifier-confirmed failures.
The submission remains **23/30 (76.7%)**, with four verifier failures and those three
unscored attempts; maintainers decide the acceptance policy.

A Runta outage before case 9 required rebuilding and continuing the same run; evaluation
inputs stayed fixed while system runc changed from 1.4.3 to 1.5.1. Also disclose Moonshot
CN versus Fireworks, shared versus per-task checkpoints, egress policy and partial usage
when comparing the candidate with the published baselines.

## Offline checks

With Python 3.12, the pinned Harbor/Pier packages and Node installed:

```bash
python -m unittest discover -s skills/frontierharness-eval/profiles/mcode -p 'test_*.py'
git diff --check
```

The tests use native configuration parsers and local runner doubles. They do not
create a runtime, call a model, execute a benchmark task or establish a ranking.
