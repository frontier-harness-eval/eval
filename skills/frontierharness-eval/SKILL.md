---
name: frontierharness-eval
description: Benchmark a third-party coding-agent harness against FrontierHarness Eval using Runta runtimes. Provisions a clean runtime bound to the GitHub repo under evaluation, installs the Harbor and Pier stacks needed for Terminal-Bench and DeepSWE tasks, freezes a golden checkpoint, runs tasks from identical fresh restores while saving trajectories as evidence, generates a comparison diagram, and builds a shareable report. Use when evaluating, benchmarking, scoring, or comparing a coding agent harness, or when the user mentions FrontierHarness, DeepSWE, Terminal-Bench, Harbor, Pier, golden checkpoints, or harness trajectories.
---

# FrontierHarness Eval for a Third-Party Harness

Score a harness that is not in the published FrontierHarness v1.0 set, on the same
tasks, runtime, and cost accounting, so the result can be placed next to the twelve
baseline configurations in `results/eval-data.json`.

## Prerequisites

Confirm all of these before touching a runtime:

```bash
runta --version                 # brew install runta-dev/tap/runta  (or npm i -g @runta/runta-cli)
echo "${RUNTA_TOKEN:?set RUNTA_TOKEN from Settings -> Runta API Keys}" | cut -c1-3
jq --version && node --version  # jq for trial parsing, node >= 18 for the report scripts
```

Run every command below from the repository root, so `results/eval-data.json`,
`benchmark.json`, and `tasks/` resolve. This repo has its own `scripts/` directory, so
address the skill's scripts through an explicit variable rather than a bare `scripts/`:

```bash
FH=skills/frontierharness-eval/scripts
```

Collect from the user before starting: harness name and version, the task subset, and
the GitHub repo and commit when the harness is installed from source. Runner-built-in
harnesses can instead pin their package and runner versions; see the MiniMax Code
profile below for a concrete example.

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
no preference. A different provider keeps the pass rate comparable, since the model is
identical; it only puts the cost column at risk, so check that the provider's input,
cached-input, and output prices match the ones in `reference.md`. The report raises this
caveat automatically. Only change the *model* if the user explicitly wants a
non-comparable run, and say so in the report.

## Workflow

Copy this checklist into your working notes and keep it updated:

```
- [ ] 1. Clean runtime created
- [ ] 2. Harness source commit or package version pinned
- [ ] 3. Benchmark stack installed and frozen as a golden checkpoint
- [ ] 4. Trials run from fresh restores, trajectories saved
- [ ] 5. Comparison diagram generated
- [ ] 6. Report built and shared
```

Steps 1 through 3 are one command (`provision-golden-checkpoint.sh`), but read the
per-step notes below because the fidelity rules live there.

### 1-3. Clean runtime, repo, and golden checkpoint

```bash
export RUNTA_TOKEN=rt_...
export FIREWORKS_API_KEY=...   # or the key for whichever --provider you pick

$FH/provision-golden-checkpoint.sh \
  --runtime fh-build \
  --checkpoint fh-golden-myharness-v1 \
  --harness my-harness \
  --provider fireworks \
  --repo https://github.com/acme/my-harness \
  --commit 9f2c1ab \
  --cpus 4 --memory 8192 \
  --prepull-tasks tasks \
  --install-script ./install-my-harness.sh
```

What the script does, and why each part matters:

- **Clean runtime.** `runta run` with no `--agent` preset, so no vendor harness is
  pre-installed and nothing competes with the harness under test.
- **Repo pinned by commit.** The harness is cloned to `/work/harness` at `--commit`.
  A branch name is not reproducible; always pin a SHA.
- **Built-in harnesses pinned by version.** If the runner owns the adapter, omit
  `--repo` and `--commit`, then pass `--harness-version` and `--harbor-version`.
- **Benchmark stack.** Installs `uv`, `harbor` for Terminal-Bench, `pier` plus the
  `deep-swe` task corpus for DeepSWE, and `runta-sdk[harbor]`.
- **Credential as a secret stub.** The provider key named by `--secret-name` (defaulted
  from `--provider`) is stored with `runta secret set` and injected by the egress proxy,
  so the real key never lands inside the runtime or inside a checkpoint. Verify with
  `runta exec fh-build -- sh -lc 'test "$FIREWORKS_API_KEY" = runta-secret-stub'`.
- **Cache warming on sample tasks only.** Docker images for the formal tasks are
  pre-pulled, but the only task ever *executed* before the checkpoint is
  `terminal-bench-sample@2.0` with Harbor's `oracle` agent. Never execute a formal task
  before the checkpoint — that is warm-cache bias and it invalidates the comparison.
- **Manifest.** `/work/manifest.json` records tool versions, the harness commit, the
  model, and image digests. It is captured inside the checkpoint and copied out, which
  is what makes a later run verifiable.
- **Golden checkpoint.** `runta checkpoint create` freezes filesystem *and* process
  state. Every trial restores from it, so all trials share one identical cold start.

Before moving on, confirm the checkpoint is ready:

```bash
runta checkpoint ls
```

### 4. Run trials and save trajectories

Each task gets its own fresh restore, then the runtime is deleted. Never reuse a
runtime across tasks.

```bash
$FH/run-trials.sh \
  --checkpoint fh-golden-myharness-v1 \
  --harness my-harness \
  --provider fireworks \
  --run-id 2026-09-02-myharness \
  --tasks tasks.txt \
  --out runs
```

Pass the same `--provider` here as at provisioning time. The checkpoint has that
provider's key name baked in as a stub, so a mismatch leaves the harness without a
credential.

`tasks.txt` holds one task id per line, prefixed by suite:

```
terminal-bench/regex-log
terminal-bench/build-cython-ext
datacurve/anko-typed-variable-bindings
```

To reproduce the published 30-task set exactly:

```bash
jq -r '.harnesses[0].task_details[].id' results/eval-data.json > tasks.txt
```

Per task the script restores the checkpoint, runs the harness through Harbor
(`terminal-bench/*`) or Pier (`datacurve/*`), copies `/work/jobs/<task>` out, writes a
normalized `trial.json`, and removes the runtime. Evidence lands in
`runs/<run-id>/trials/<task>/` and includes the agent trajectory, verifier logs, the
`model.patch` artifact, and the raw runner stdout. Keep it — the report links to it and
it is the only proof a score is real.

If a trial dies on infrastructure rather than the task, mark it and rerun it rather
than scoring it as a failure:

```bash
# Re-running an existing --run-id with the same configuration only replaces the tasks
# listed, leaving the rest. Use a new run ID when checkpoint/provider/model changes.
echo "terminal-bench/<task>" > retry.txt
$FH/run-trials.sh --checkpoint fh-golden-myharness-v1 --harness my-harness \
  --run-id 2026-09-02-myharness --tasks retry.txt --out runs

# If it fails on infrastructure again, mark it so it is excluded rather than scored.
trial=runs/2026-09-02-myharness/trials/terminal-bench-<task>/trial.json
jq '.status = "infra_invalid" | .success = false' "$trial" > "$trial.tmp" && mv "$trial.tmp" "$trial"
```

### 5. Generate the diagram

```bash
node $FH/normalize-results.mjs --run runs/2026-09-02-myharness --label "My Harness"
node $FH/generate-chart.mjs   --run runs/2026-09-02-myharness
```

`normalize-results.mjs` folds the trials into `candidate.json` using the same field
names and definitions as `results/eval-data.json`, so the candidate slots directly into
the baseline set. `generate-chart.mjs` writes
`runs/<run-id>/report/chart.svg`: a pass-rate versus cost scatter with the twelve
baselines muted and the candidate highlighted, plus a pass-rate ranking panel.

### 6. Build and share the report

```bash
node $FH/build-report.mjs --run runs/2026-09-02-myharness
```

This writes `runs/<run-id>/report/REPORT.md` and a self-contained
`runs/<run-id>/report/index.html` with the chart inlined, so a single file can be
attached or opened anywhere. Both end with a link back to the source evaluation at
<https://frontierharness.org/>.

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
| Provider token prices matching the baselines, or a stated caveat | Pass rate survives a provider swap; the cost column does not |
| One golden checkpoint per task set, every trial a fresh restore | Identical cold start, identical disk and memory state |
| Identical vCPU, memory, and disk across all restores | Compute differences show up as time and pass-rate differences |
| No formal task executed before the checkpoint | Prevents warm-cache bias |
| Canonical result is the first valid attempt | Matches `benchmark.json` `canonical_selection` |
| Infra failures marked `infra_invalid`, not `failure` | A crashed runtime is not a harness failure |

Cost comparability has one caveat worth repeating in every report: baseline costs in
`results/eval-data.json` reprice first-turn cache reads consistently across harnesses.
`effective_cost_per_pass` (total cost over all tasks divided by passes) is reproducible
from raw per-task cost and is the safe field to compare. The `*_normalized` fields are
not reproducible from public data — the scripts leave them null rather than inventing
values.

## Metric definitions

`normalize-results.mjs` computes these from `trial.json` files, matching the baseline:

| Field | Definition |
| --- | --- |
| `pass_rate` | passes / tasks attempted |
| `effective_cost_per_pass` | total cost across *all* tasks / passes |
| `median_cost_per_success` | median per-task cost over successful tasks only |
| `median_duration_seconds` | median wall-clock over successful tasks only |
| `cache_hit_rate_typical` | median cache hit rate over successful tasks only |
| `mean_turns` | mean agent turns over successful tasks only |

## Additional resources

- Command reference, runner templates, and troubleshooting: [reference.md](reference.md)
- MiniMax Code through Harbor: [minimax-code.md](minimax-code.md)
- Published results and task definitions: `results/eval-data.json`, `tasks/<task>/task.toml`
- Source evaluation: <https://frontierharness.org/>
