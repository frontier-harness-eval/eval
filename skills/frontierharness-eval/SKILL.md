---
name: frontierharness-eval
description: Benchmark a third-party coding-agent harness against FrontierHarness Eval using Runta runtimes. Provisions a clean runtime bound to the GitHub repo under evaluation, installs the Harbor and Pier stacks needed for Terminal-Bench and DeepSWE tasks, freezes a golden checkpoint, runs tasks from identical fresh restores while saving trajectories as evidence, generates a comparison diagram, and builds a shareable report. Use when evaluating, benchmarking, scoring, or comparing a coding agent harness, or when the user mentions FrontierHarness, DeepSWE, Terminal-Bench, Harbor, Pier, golden checkpoints, or harness trajectories.
---

# FrontierHarness Eval for a Third-Party Harness

Score a harness that is not in the published FrontierHarness v1.0 set, on the same
tasks, runtime, and cost accounting, so the result can be placed next to the twelve
baseline configurations in `results/eval-data.json`.

## Workspace setup

`npx skills add frontier-harness-eval/eval --skill frontierharness-eval` installs this
skill and its scripts, but not the repository's task definitions or baseline results.
Prepare those files before following the evaluation workflow.

Set `FH` to the absolute path of the `scripts/` directory beside the `SKILL.md` you
loaded. Use that installed copy even after changing the working directory; the install
location varies by agent and by project/global scope. For example, replace this path
with the actual location:

```bash
FH="/absolute/path/to/frontierharness-eval/scripts"
```

If the current directory already contains `benchmark.json`, `results/eval-data.json`,
and `tasks/`, use it as the benchmark workspace. An existing repository checkout or a
workspace created by `npx @frontierharness/eval` both qualify. Otherwise reuse a known
checkout, or create one with Git:

```bash
git clone https://github.com/frontier-harness-eval/eval.git frontierharness-eval
cd frontierharness-eval
```

If that destination already exists, inspect it and reuse it if complete, or choose a
new directory; do not overwrite existing work. Run the commands below from the
benchmark workspace so data paths and `runs/` resolve there. Keep `FH` pointing to
the installed skill's scripts, not the repository's unrelated top-level `scripts/`.

## Prerequisites

Use the official [Runta skills](https://runta.com/docs/skills/) for Runta setup and
command guidance. Install them in the same agent and scope as this skill if needed:

```bash
npx skills add https://runta.com/docs --skill runta-installer runta-cli
```

Read `runta-installer` when the Runta CLI needs installation or authentication setup;
this evaluation requires the local CLI, and its provisioning script installs the
runtime's SDK dependencies. Read `runta-cli` when checking runtime commands or
troubleshooting Runta operations. If these skills are unavailable, use the linked
Runta docs and the checks below. Keep this skill's benchmark requirements: prepare a
clean runtime without an agent preset, freeze one golden checkpoint, and use a fresh
restore per task with the specified resources.

Confirm all of these before touching a runtime:

```bash
runta --version                 # brew install runta-dev/tap/runta  (or npm i -g @runta/runta-cli)
runta checkpoint ls             # any API call proves the CLI is authenticated
jq --version && node --version  # jq for trial parsing, node >= 18 for the report scripts
```

Collect from the user before starting: harness name and version, the GitHub repo and
commit for the harness under evaluation, and the task subset.

**The model is not a variable; the provider is.** FrontierHarness holds the model
constant at **Kimi K3** so the harness is the only thing that differs. Which provider
serves it is up to the user, selected with `--provider`. The scripts warn if the model
is not Kimi K3, and refuse an unknown provider name.

| `--provider` | Model route | Key to collect |
| --- | --- | --- |
| `fireworks` (default, used by the published baselines) | `fireworks_ai/accounts/fireworks/models/kimi-k3` | `FIREWORKS_API_KEY` |
| `moonshot` | `moonshot/kimi-k3` | `MOONSHOT_API_KEY` |
| `openrouter` | `openrouter/moonshotai/kimi-k3` | `OPENROUTER_API_KEY` |
| `together` | `together_ai/moonshotai/Kimi-K3` | `TOGETHER_API_KEY` |
| `custom` | supply `--model` | supply `--secret-name` |

Ask which provider the user has a key for, and use `--provider fireworks` if they have
no preference. A different provider must be documented and validated with a matched control;
matching the model name alone does not prove equivalent serving behavior. Costs use
the frozen benchmark token prices in `reference.md`, regardless of the provider's
actual billing rates. Only change the *model* if the user explicitly wants a
non-comparable run, and say so in the report.

## Runtime quota and concurrency

This tenant's shared maximum is **32 vCPUs and 64 GB RAM across all runtimes**,
not per instance. Leave headroom below both limits; do not create enough instances
to fill the quota.

- Before creating or restoring a runtime, inspect `runta ps -a` and account for
  existing CPU and memory allocations plus the proposed runtime. Include build
  runtimes, trials retained for recovery, other evaluations, and unrelated workloads.
  If available capacity is unclear, resolve it before provisioning.
- Run trials sequentially by default. Only increase concurrency when the combined
  allocations leave headroom under both limits, and recheck before each allocation.
  Preserve the benchmark's per-runtime resources; reduce concurrency instead of
  shrinking trial runtimes to fit.
- Remove this evaluation's build runtime after the checkpoint and checks succeed.
  Remove completed trial runtimes only after their evidence is verified locally.
  Recover retained attempts before cleanup, and leave unrelated runtimes alone.
  If capacity is insufficient or `RESOURCE_EXHAUSTED` occurs, stop provisioning,
  wait for capacity or safely clean up this evaluation's finished runtimes, then
  recheck usage before retrying.

## Workflow

Copy this checklist into your working notes and keep it updated:

```
- [ ] 1. Clean runtime created
- [ ] 2. Harness repo cloned at a pinned commit
- [ ] 3. Benchmark stack installed and frozen as a golden checkpoint
- [ ] 4. Trials run from fresh restores, trajectories saved
- [ ] 5. Comparison diagram generated
- [ ] 6. Report built and shared
```

Steps 1 through 3 are one command (`provision-golden-checkpoint.sh`), but read the
per-step notes below because the fidelity rules live there.

### 1-3. Clean runtime, repo, and golden checkpoint

Authenticate the CLI with `runta login`, or set `RUNTA_TOKEN` if you prefer an
explicit token. The provider key only has to be exported the first time: it is stored as
a tenant secret, and the API never hands the value back, so a later re-cut of the
checkpoint reuses the stored secret instead of demanding the plaintext again.

```bash
export FIREWORKS_API_KEY=...   # or the key for whichever --provider you pick

bash "$FH/provision-golden-checkpoint.sh" \
  --runtime fh-build \
  --checkpoint fh-golden-myharness-v1 \
  --harness my-harness \
  --provider fireworks \
  --repo https://github.com/acme/my-harness \
  --commit 9f2c1ab \
  --cpus 4 --memory 8192 --disk-size-gib 50 --keep-runtime \
  --install-script ./install-my-harness.sh
```

What the script does, and why each part matters:

- **Clean runtime.** `runta run` with no `--agent` preset, so no vendor harness is
  pre-installed and nothing competes with the harness under test. Disk defaults to
  50 GiB: building a harness from source plus a task image can overflow the 16 GiB
  Runtime Image default. Keep it at 50 GiB so every trial restores with the same
  capacity.
- **Repo pinned by commit.** The harness is cloned to `/work/harness` at `--commit`.
  A branch name is not reproducible; always pin a SHA.
- **Benchmark stack.** Installs `uv`, Harbor `0.22.0` for Terminal-Bench, `datacurve-pier==0.3.1` plus the `deep-swe` corpus at commit **`435ee89ec2f2e2289f33b0da4f992f0b7b7266b9`** (the published `v1.1` label is not a Git tag; see the [corpus caveat](reference.md#corpus-pin-and-pi-control)), and `runta-sdk[harbor]`.
- **Credential as a secret stub.** The provider key named by `--secret-name` (defaulted
  from `--provider`) is stored with `runta secret set` and injected by the egress proxy,
  so the real key never lands inside the runtime or inside a checkpoint. The script also
  allowlists the provider host plus the benchmark registry, source download hosts,
  and package registries required by verifiers. This runtime policy also permits
  agent package downloads, subject to Harbor/Pier isolation. The shared host list
  lives in `scripts/providers.sh`; see [trial network access](reference.md#trial-network-access).
  Installation and image pulls happen before this restriction; egress setup errors
  stop preparation instead of silently falling back to a broken policy. Verify with
  `runta exec fh-build -- sh -lc 'test "$FIREWORKS_API_KEY" = runta-secret-stub'`.
- **Small checkpoint, per-trial image pulls.** Formal task images are pulled after
  each fresh restore. Pre-pulling the full corpus has produced roughly 22 GiB of images
  and stalled checkpoint creation; `--prepull-tasks` remains an explicit opt-in with a
  warning. The only task ever *executed* before the checkpoint is
  `terminal-bench-sample@2.0` with Harbor's `oracle` agent. Never execute a formal task
  before the checkpoint — that is warm-cache bias and it invalidates the comparison.
- **Container runtime workaround.** Restores the known Runta wrapper symlink
  `/usr/local/sbin/runc` to `/usr/bin/runc` to avoid the reported injected-init hang
  during Pier verifier builds. Unknown binaries are left intact. Use
  `--keep-runta-runc` to disable the workaround; the manifest records the choice and
  resolved binary path. Harbor retains its explicit CA overlay.
- **Manifest.** `/work/manifest.json` records tool versions, the harness and corpus
  commits, model, topology, image policy, and resolved runc path. Each trial's
  `restore.log` records its image pull output, including the registry digest. Keep
  both the manifest and logs to audit a later run.
- **Golden checkpoint.** `runta checkpoint create` freezes filesystem *and* process
  state. The script waits up to `--checkpoint-timeout` (default 900 seconds) for
  `ready` and retains the build runtime on failure. Each trial restores from it, then
  pulls its own image before launching the harness.

Before moving on, confirm the checkpoint is ready:

```bash
runta checkpoint ls
```

The example uses `--keep-runtime` so the build runtime remains available for the
stub and manifest checks. After confirming the checkpoint is ready, remove the build
runtime with `runta rm fh-build`.

For an agent absent from Harbor or Pier, register it in both runner registries through
`--install-script` and pass its registered name as `--harness`. Service-based harnesses
are supported: set `--harness-topology runtime-service` or `external-service`, document
the service version and resources, and ensure task state is reset between restores.
The report discloses the topology difference from the container CLI baselines.

### 4. Run trials and save trajectories

Before a full sweep, preflight the harness's actual tool calls and both the agent's
and verifier's dependency paths under the intended task isolation. A reachable model
endpoint alone is insufficient. For offline source caches, native tool validation, and
distinguishing verifier infrastructure failures from wrong answers, read
[isolated evaluation repairs](isolated-evaluation-repairs.md). Preserve original
tests, prompts, timeouts, and raw results; record repairs in a new run variant.

Each task gets its own fresh restore. The runtime is deleted only after complete
evidence is verified locally and the trial record is written. Never reuse a
runtime across tasks.

```bash
bash "$FH/run-trials.sh" \
  --checkpoint fh-golden-myharness-v1 \
  --harness my-harness \
  --provider fireworks \
  --run-id 2026-09-02-myharness \
  --out runs
```

Pass the same `--provider` here as at provisioning time. The checkpoint has that
provider's key name baked in as a stub, so a mismatch leaves the harness without a
credential.

With no `--tasks`, the script runs every task defined in this repo's `tasks/` directory,
reading the suite-prefixed id out of each `tasks/<task>/task.toml`. That is the published
30-task set. The trial script pulls just the selected image before restricting egress.
DeepSWE images come from the pinned corpus; Terminal-Bench images come from the
selected task directory, or this repository when `--tasks` is a list file.

To run a subset, point `--tasks` at a file holding one suite-prefixed id per line:

```
terminal-bench/regex-log
terminal-bench/build-cython-ext
datacurve/anko-typed-variable-bindings
```

A subset is not comparable to the published leaderboard; say so in the report.

`run.json` records the trial `egress_policy` (mode, runtime scope, and exact hosts).
The published baselines' applied policy is unknown, so new runs default to
`methodology_comparable: false` and receive no leaderboard rank, even with all 30
tasks. Use a matched control with the same policy and environment before claiming
comparability. A changed or unrecorded policy requires a new run id; do not relabel
old trial evidence with the new policy. Recover retained trials using the original
script version and configuration.

Per task the script restores the checkpoint, runs the harness through Harbor
(`terminal-bench/*`) or Pier (`datacurve/*`), copies `/work/jobs/<task>` out, writes a
normalized `trial.json`, and removes the runtime after verifying the evidence archive
SHA-256. Execution is
detached with a remote timeout and durable exit record. Transport retries reconnect
to the same attempt; they never restart the harness. Evidence lands in
`runs/<run-id>/trials/<task>/` and includes the agent trajectory, verifier logs, the
`model.patch` artifact, and the raw runner stdout. Keep it — the report links to it and
it is the only proof a score is real.

If transport fails, the script records `infra_invalid` with `recovery: true` and
retains the runtime. Re-run the same command to collect the original attempt. Valid
passes and failures (including post-execution timeouts) are preserved as the first valid attempt. Use a new
`--run-id` for an intentional new experiment. If infrastructure failed before launch,
retry the affected task rather than scoring it as a failure. The collector classifies
raw evidence automatically; do not override `trial.json` status by hand:

```bash
# Resume pending work or retry infra-invalid setup; keep all valid attempts.
echo "terminal-bench/<task>" > retry.txt
bash "$FH/run-trials.sh" --checkpoint fh-golden-myharness-v1 --harness my-harness \
  --provider fireworks --run-id 2026-09-02-myharness --tasks retry.txt --out runs

```

### 5. Generate the diagram

```bash
node "$FH/normalize-results.mjs" --run runs/2026-09-02-myharness --label "My Harness"
node "$FH/generate-chart.mjs"    --run runs/2026-09-02-myharness
```

`normalize-results.mjs` folds the trials into `candidate.json` using the same field
names and definitions as `results/eval-data.json`, so the candidate slots directly into
the baseline set. `generate-chart.mjs` writes
`runs/<run-id>/report/chart.svg`: a pass-rate versus cost scatter with the twelve
baselines muted and the candidate highlighted, plus a pass-rate ranking panel.

### 6. Build and share the report

```bash
node "$FH/build-report.mjs" --run runs/2026-09-02-myharness
```

This writes `runs/<run-id>/report/REPORT.md` and a self-contained
`runs/<run-id>/report/index.html` with the chart inlined, so a single file can be
attached or opened anywhere. Both end with a link back to the source evaluation at
<https://frontierharness.org/>.

#### Report visual style

Use [frontierharness.org](https://frontierharness.org/) as the visual reference for
reports. The bundled `build-report.mjs` and `generate-chart.mjs` implement this style:

- Pure black background, off-white primary text, muted gray secondary text, thin
  charcoal dividers, and restrained orange (`#f47b35`) highlights.
- System sans-serif headings and harness names; monospace labels, ranks, metadata,
  and tabular numbers. Keep the layout spacious and flat, with square edges.
- Lead with the candidate summary and comparison chart, then section navigation,
  four compact result metrics, comparison rows, numbered methodology notes, and
  task evidence. Keep wide charts and tables horizontally scrollable on phones.
- Use orange to identify the candidate and key links. Preserve visible subset and
  methodology caveats and the existing rules for excluding non-comparable candidates.
- Keep HTML self-contained with inline CSS/SVG and system font fallbacks. The
  Markdown version remains a portable content equivalent. Retain the report's
  actual metric definitions (including effective cost per pass); the reference
  site's visual style does not justify changing accounting or copying its scores.

After changing the report template, generate a report from existing candidate data
and inspect the HTML at desktop and narrow widths before sharing.

Share it with whichever path fits:

```bash
# Public link, no repo access needed
gh gist create runs/<run-id>/report/REPORT.md runs/<run-id>/report/chart.svg --public \
  --desc "FrontierHarness Eval: My Harness"

# Single portable file
open runs/<run-id>/report/index.html

# Commit alongside the published results
git add runs/<run-id> && git commit -m "add My Harness evaluation"
```

## Reproducibility rules

A result is only comparable to the published leaderboard if all of these hold. State
explicitly in the report which ones were relaxed.

| Rule | Why |
| --- | --- |
| Kimi K3, the same model as every published configuration, from any provider serving it | Harness effects and model effects are otherwise inseparable |
| Frozen benchmark price table, with overrides disclosed | Compare standardized costs; actual provider billing may differ |
| One golden checkpoint per task set, every trial a fresh restore | Identical cold start, identical disk and memory state |
| Identical vCPU, memory, and disk (50 GiB) across all restores | Compute differences show up as time and pass-rate differences |
| No formal task executed before the checkpoint | Prevents warm-cache bias |
| Canonical result is the first valid attempt | Matches `benchmark.json` `canonical_selection` |
| Evidence-based validity | Verifier reward plus model usage establishes a quality outcome. A timeout after agent execution starts is a valid failure even without usage; unproven execution, setup errors, and missing verifier outcomes otherwise remain `infra_invalid` |
| One shared golden checkpoint for third-party runs | The published 360 cells used per-task checkpoints. This workflow normally pulls images after each restore; the report discloses this difference |
| Harness execution topology recorded | Custom agents may run as container CLIs, runtime services, or external services. Registration alone does not establish equivalent resource limits, isolation, or state reset |
| Exact trial egress policy recorded and held fixed for candidate and control | Package access can change task outcomes. The published baselines' applied allowlist is unknown; new reproduction runs default to unranked |

## Accounting and canonical selection

The scripts follow the frozen benchmark’s scoring and aggregation conventions:

- Filter to `benchmark.json` `task_ids`, exclude attempt numbers other than 1 and
  labels containing `warm` or starting with `smoke`, and select the earliest valid
  outcome per task. Later valid retries cannot replace it. Retain the latest invalid
  cell when no valid outcome exists. Never edit raw outcomes to manufacture validity.
- A verifier reward of at least 1 plus observed model usage is a success, even when
  the agent also raised an exception. Other verifier outcomes with usage are failures.
  A timeout after `agent_execution.started_at` is a failure even without usage or
  verifier output. All other unproven outcomes are infrastructure-invalid.
- Price total input as fresh + cache read + cache write with the bundled frozen
  table. Preserve agent-reported billing as diagnostic/fallback data. Reprice only
  first-call cached reads at the fresh rate for `cost_first_cold_usd`; missing
  first-call details leave that value null. Retained per-call evidence supports
  normalized costs and cache metrics; missing values are never invented.
- Success-only efficiency metrics require 100% successful-cell coverage. Coverage
  denominators for duration, turns, tokens, cache, and success cost are successes.
  `cost_per_success_normalized` is the arithmetic mean first-cold cost of successes;
  `median_cost_per_success_normalized` is their median.
- `effective_cost_per_pass` sums known first-cold costs across all canonical cells
  and divides by passes, including failed and invalid cells with known costs.
  This field can be partial: report `effective_cost_coverage` (known-cost cells /
  expected tasks) beside it. It is distinct from success-only mean cost.
- `cache_hit_rate_normalized` is token-weighted `(cached - first_cached) / input`
  across successes. `cache_hit_rate_typical` is the median per-success normalized
  rate; quartiles use inclusive interpolation. Raw and session-only cache rates
  are retained separately on trials.
- `median_duration_seconds` is median full runner trial wall time over successes,
  from raw start/finish timestamps; a cell watchdog uses its configured limit.
  It is not model latency. Turns count model calls from per-call harness records.
- `pass_rate` is passes / valid cells; `success_rate_expected` is passes / expected
  tasks; `valid_coverage` is valid / expected. Missing and invalid cells stay visible.
  Full coverage requires a valid canonical cell for every frozen task identity.

Before sharing, review invalid cells, successful cells with exceptions, missing
successful-cell metrics, zero-usage outcomes, and duration/token/turn/cache/cost
outliers. A flag requires evidence review, not automatic exclusion. Preserve raw
results and recovery evidence. Do not call an incomplete matrix complete.

Accounting alignment does not establish environment equivalence. The shared
checkpoint, registry-resolved Terminal-Bench tasks, corpus image differences,
provider route, topology, and trial egress must be matched with a control before
claiming leaderboard comparability. New runs remain unranked by default.

## Additional resources

- Command reference, runner templates, and troubleshooting: [reference.md](reference.md)
- Published results and task definitions: `results/eval-data.json`, `tasks/<task>/task.toml`
- Source evaluation: <https://frontierharness.org/>
