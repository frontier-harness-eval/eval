<h1 align="center">FrontierHarness Eval</h1>

<p align="center">
  <a href="https://frontierharness.org"><img alt="Live leaderboard" src="https://img.shields.io/badge/live-leaderboard-ff6418?style=flat-square" /></a>
  <img alt="Benchmark version" src="https://img.shields.io/badge/benchmark-v1.0-222222?style=flat-square" />
  <img alt="Kimi K3" src="https://img.shields.io/badge/model-Kimi_K3-5019c5?style=flat-square" />
  <img alt="10 harnesses" src="https://img.shields.io/badge/harnesses-10-1267c4?style=flat-square" />
  <img alt="13 configurations" src="https://img.shields.io/badge/configurations-13-3979b8?style=flat-square" />
  <img alt="30 tasks" src="https://img.shields.io/badge/tasks-30-168a7d?style=flat-square" />
  <img alt="390 runs" src="https://img.shields.io/badge/evaluations-390-222?style=flat-square" />
</p>

<p align="center">
  <a href="https://frontierharness.org"><strong>Explore the live results →</strong></a>
  &nbsp;·&nbsp;
  <a href="https://runta.com/blog/introducing-frontierharness-eval/"><strong>Read the blog →</strong></a>
  &nbsp;·&nbsp;
  <a href="#evaluate-your-own-harness"><strong>Evaluate your own harness →</strong></a>
</p>

<div align="center"><img src="assets/divider.svg" width="100%" height="1" alt="" /></div>

<div align="center">
  <a href="https://frontierharness.org">
    <img src="assets/frontier-harness-chart.svg" width="100%" alt="FrontierHarness Eval benchmark: pass rate versus median cost per task across ten harnesses and thirteen configurations" />
  </a>
</div>

<div align="center"><img src="assets/divider.svg" width="100%" height="1" alt="" /></div>

## Similar pass rate. 26.7-point pass-rate spread.

We ran the same **Kimi K3** model through ten coding-agent harnesses—13 configurations in total—on the same 30 software-engineering tasks. With the model and tasks held constant, changing the harness configuration changed pass rate, cost, cache behavior, and speed.

<div align="center">
  <a href="https://frontierharness.org">
    <img src="assets/frontier-harness-leaders.svg" width="100%" alt="FrontierHarness Eval leaders: KOT for quality and speed, Pi for balance, and Exo Harness for cost" />
  </a>
</div>

### Full results

| Harness (configuration) | Pass rate | Median cost per pass | Cache, median cell | Median time |
| --- | --- | --- | --- | --- |
| **KOT** | **76.7%** | **$2.83** | 94.1% | 5m 0s |
| Codex | 66.7% | $3.47 | 88.0% | 6m 43s |
| DSH Creator | 63.3% | $3.28 | 84.3% | 6m 44s |
| Claude Code | 63.3% | $18.34 | 67.8% | 9m 38s |
| Pi | 60.0% | $2.43 | 79.4% | 7m 33s |
| DSH PTC | 60.0% | $4.58 | 87.2% | 7m 44s |
| DSH Standard | 60.0% | $3.46 | 86.5% | 6m 17s |
| Oh My Pi | 56.7% | $4.75 | 82.2% | 6m 46s |
| Kimi Code | 56.7% | $3.65 | 88.0% | 7m 56s |
| DSH Minimal | 56.7% | $4.72 | 84.6% | 5m 41s |
| Exo Harness | 53.3% | **$1.05** | 70.3% | 6m 17s |
| OpenCode | 50.0% | $3.24 | 78.4% | 6m 27s |
| Hermes | 50.0% | $2.90 | 85.9% | 6m 58s |

The [interactive report](https://frontierharness.org) includes failed runs, total cost per task, cache behavior, speed, and task-level results. For the evaluation design and analysis, read the [launch article](https://runta.com/blog/introducing-frontierharness-eval/).

## What is in this repository

```text
.
├── benchmark.json              # Public benchmark definition
├── cli/index.mjs               # `npx @frontierharness/eval`: workspace + skill installer
├── metadata/
│   ├── difficulty.json         # Difficulty assignments and source methodology
│   └── harness-versions.json   # Harness versions used for the run
├── results/
│   └── eval-data.json          # Normalized aggregate and task-level results
├── tasks/<task>/
│   ├── instruction.md          # Prompt shown to every harness
│   └── task.toml               # Public task metadata and environment definition
└── skills/frontierharness-eval/  # Agent-neutral skill, usable by hand
    ├── SKILL.md                # Evaluation workflow for a third-party harness
    ├── PROMPT.md               # Copy-paste prompt that points an agent at the skill
    ├── reference.md            # Command reference, runner templates, troubleshooting
    └── scripts/                # Provisioning, trial runner, scoring, chart, report
```

The repository intentionally contains **results, task definitions, and the evaluation workflow**. Internal infrastructure, credentials, runtime identifiers, private evidence, solutions, and deployment configuration are not included.

## Evaluate your own harness

The workflow that produced the table above ships with this repository, so a harness that is not in it can be scored on the same tasks, runtime, and cost accounting, then placed directly next to the twelve baseline configurations.

[`skills/frontierharness-eval/`](skills/frontierharness-eval/) is an agent-neutral skill: point any coding agent that reads `SKILL.md` at it and it will drive the whole run — freezing the golden checkpoint, running every task from an identical fresh restore, scoring the trials, and building the report.

## How to use the skill

### Let an agent drive it

Clone this repository and open it in any coding agent:

```bash
git clone https://github.com/frontier-harness-eval/eval.git
```

Ask the agent to evaluate your harness:

```text
use the skill located in the repo to evaluate [your harness github link]
```

<details>
<summary><strong>Run it by hand instead</strong></summary>

The skill's scripts are the same ones an agent would call, so the run works without an agent at all. Every path is relative to the workspace root, and this repo has its own `scripts/` directory, so address the skill's scripts through a variable:

```bash
FH=skills/frontierharness-eval/scripts
```

**1. Prerequisites.** The `runta` CLI (`brew install runta-dev/tap/runta` or `npm i -g @runta/runta-cli`) authenticated with `runta login`, plus `jq` and node >= 18.

**2. Install script.** Write a script that builds your harness on a clean Linux box. If it is not a built-in agent for Harbor or Pier, register it as a custom agent in both runner registries there, and use the registered name as `--harness`.

**3. Provider key.** Store it once as a [Runta secret](https://runta.com/docs/runtime/secrets-and-secret-injection/), named after the env var for your provider (`FIREWORKS_API_KEY`, `MOONSHOT_API_KEY`, `OPENROUTER_API_KEY`, or `TOGETHER_API_KEY`). The interactive prompt keeps the value out of your shell history:

```bash
runta secret set FIREWORKS_API_KEY --prompt
```

The API never hands the value back, so provisioning reuses the stored secret instead of asking for plaintext again. A `--value-env` or `--value-stdin` route works too if you already have the key in the environment.

**4. Golden checkpoint.** One command creates the clean runtime, clones the harness at a pinned commit, installs the Harbor and Pier stacks, pre-pulls the task images, and freezes the checkpoint:

```bash
$FH/provision-golden-checkpoint.sh \
  --runtime fh-build --checkpoint fh-golden-myharness-v1 \
  --harness my-harness --provider fireworks \
  --repo https://github.com/acme/my-harness --commit 9f2c1ab \
  --cpus 4 --memory 8192 --disk-size-gib 100 \
  --prepull-tasks tasks --install-script ./install-my-harness.sh
```

The real key stays in the egress proxy, so confirm the runtime only ever sees a stub:

```bash
runta exec fh-build -- sh -lc 'test "$FIREWORKS_API_KEY" = runta-secret-stub'
```

**5. Trials.** Each task gets its own fresh restore, which is then deleted. With no `--tasks`, this runs the published 30-task set read from `tasks/`:

```bash
$FH/run-trials.sh \
  --checkpoint fh-golden-myharness-v1 --harness my-harness \
  --provider fireworks --run-id 2026-09-02-myharness --out runs
```

Pass a file of suite-prefixed ids to `--tasks` to run a subset — worth doing first with one Terminal-Bench and one DeepSWE task to prove the plumbing before spending the full budget. Re-running the same `--run-id` replaces only the tasks you list. If a trial dies on infrastructure twice, mark it rather than scoring it as a failure:

```bash
trial=runs/2026-09-02-myharness/trials/terminal-bench-<task>/trial.json
jq '.status = "infra_invalid" | .success = false' "$trial" > "$trial.tmp" && mv "$trial.tmp" "$trial"
```

**6. Score, chart, and report.**

```bash
node $FH/normalize-results.mjs --run runs/2026-09-02-myharness --label "My Harness"
node $FH/generate-chart.mjs    --run runs/2026-09-02-myharness
node $FH/build-report.mjs      --run runs/2026-09-02-myharness
```

Per-step reasoning, runner templates, and troubleshooting are in [`SKILL.md`](skills/frontierharness-eval/SKILL.md) and [`reference.md`](skills/frontierharness-eval/reference.md).

</details>

## Keeping a result comparable

A score only belongs next to the published numbers if the run holds these invariants. The report states any that were relaxed.

- **Kimi K3**, the same model every published configuration used, otherwise harness effects and model effects are inseparable. Any provider serving it is fine for pass rate; for cost, check its token prices match the ones in [`reference.md`](skills/frontierharness-eval/reference.md).
- **One golden checkpoint, one fresh restore per task**, with identical vCPU, memory, and disk on every restore.
- **No formal task executed before the checkpoint is frozen.** Pre-pulling images is environment prep; running a task early is warm-cache bias. The provisioning script only ever warms on `terminal-bench-sample`.
- **Infrastructure failures marked `infra_invalid`**, not scored as task failures.

Cost is compared on `effective_cost_per_pass`, which is total cost across all tasks divided by passes and is reproducible from raw per-task cost. The `*_normalized` fields in `results/eval-data.json` reprice first-turn cache reads using data that is not public, so the scoring script leaves them empty rather than inventing values.

Metric definitions and the trial record contract are in [`SKILL.md`](skills/frontierharness-eval/SKILL.md). Runner templates, the alternative Harbor-with-Runta-provider topology, and troubleshooting are in [`reference.md`](skills/frontierharness-eval/reference.md).

## Methodology

### Tested harness configurations

| Configuration | Version | Configuration | Version |
|---|---:|---|---:|
| Codex | `0.148.0` | DSH Creator | `0.1.0-rc.8` |
| Claude Code | `2.1.237` | DSH Minimal | `0.1.0-rc.8` |
| Pi | `0.84.2` | DSH PTC | `0.1.0-rc.8` |
| DSH Standard | `0.1.0-rc.8` | Oh My Pi | `17.4.0` |
| Kimi Code | `0.37.2` | Exo Harness | `0.1.0` |
| OpenCode | `1.18.19` | Hermes | `0.20.4` |
| KOT | `1.3.1` | | |

<div align="center"><img src="assets/divider.svg" width="100%" height="1" alt="" /></div>

- FrontierHarness v1.0 focuses on software engineering contexts and terminal-based tasks. It may not generalize to other areas of knowledge work.
- Evaluated in isolated agent runtimes with the task-specific resource and network settings declared in `task.toml`.
- Kimi K3 serving endpoints: [Fireworks](https://fireworks.ai/) and [Moonshot AI](https://www.moonshot.ai/).

### Benchmark scope

- **30 tasks:** 21 Terminal-Bench tasks and 9 DeepSWE tasks
- **10 harnesses:** Claude Code, Codex, DeepSeek Harness, Exo Harness, Hermes, Kimi Code, KOT, Oh My Pi, OpenCode, and Pi
- **13 configurations:** one canonical result for every task and harness-configuration pair
- **390 evaluations:** complete task-by-configuration coverage
- **Deterministic scoring:** verifier-based pass/fail outcomes
- **Cost:** calculated from reported token usage and configuration-specific token prices

See [`benchmark.json`](benchmark.json) for the public benchmark definition and [`results/eval-data.json`](results/eval-data.json) for the complete normalized result set.

## Use the data

```bash
jq '.harnesses[] | {name, successful, effective_cost_per_pass}' results/eval-data.json
```

Every task directory contains the exact public instruction and task metadata used by the benchmark.

<div align="center"><img src="assets/divider.svg" width="100%" height="1" alt="" /></div>

## Sponsor

Runta provided the isolated runtimes and Golden Checkpoint restores used across all 360 evaluations.

<p align="center">
  <a href="https://runta.com"><img src="assets/runta-sponsor.svg" width="300" alt="Sponsored by Runta" /></a>
</p>
