<h1 align="center">FrontierHarness Eval</h1>

<p align="center">
  <a href="https://frontierharness.org"><img alt="Live leaderboard" src="https://img.shields.io/badge/live-leaderboard-ff6418?style=flat-square" /></a>
  <img alt="Benchmark version" src="https://img.shields.io/badge/benchmark-v1.0-222222?style=flat-square" />
  <img alt="Kimi K3" src="https://img.shields.io/badge/model-Kimi_K3-5019c5?style=flat-square" />
  <img alt="9 harnesses" src="https://img.shields.io/badge/harnesses-9-1267c4?style=flat-square" />
  <img alt="12 configurations" src="https://img.shields.io/badge/configurations-12-3979b8?style=flat-square" />
  <img alt="30 tasks" src="https://img.shields.io/badge/tasks-30-168a7d?style=flat-square" />
  <img alt="360 runs" src="https://img.shields.io/badge/evaluations-360-222?style=flat-square" />
</p>

<p align="center">
  <a href="https://frontierharness.org"><strong>Explore the live results →</strong></a>
  &nbsp;·&nbsp;
  <a href="https://runta.com/blog/introducing-frontierharness-eval/"><strong>Read the blog →</strong></a>
</p>

<div align="center"><img src="assets/divider.svg" width="100%" height="1" alt="" /></div>

<div align="center">
  <a href="https://frontierharness.org">
    <img src="assets/frontier-harness-chart.svg" width="100%" alt="FrontierHarness Eval benchmark: pass rate versus median cost per task across nine harnesses and twelve configurations" />
  </a>
</div>

<div align="center"><img src="assets/divider.svg" width="100%" height="1" alt="" /></div>

## Similar pass rate. 17.5x cost differences.

We ran the same **Kimi K3** model through nine coding-agent harnesses—12 configurations in total—on the same 30 software-engineering tasks. With the model, tasks, and runtime held constant, changing the harness changed pass rate, cost, cache behavior, and speed.

<div align="center">
  <a href="https://frontierharness.org">
    <img src="assets/frontier-harness-leaders.svg" width="100%" alt="FrontierHarness Eval leaders: Codex for quality, Pi for balance, Exo Harness for cost, and DSH Minimal for speed" />
  </a>
</div>

### Full results

| Harness (configuration) | Pass rate | Median cost per pass | Cache, median cell | Median time |
| --- | --- | --- | --- | --- |
| **Codex** | **66.7%** | $3.47 | 88.0% | 6m 43s |
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
├── metadata/
│   ├── difficulty.json         # Difficulty assignments and source methodology
│   └── harness-versions.json   # Harness versions used for the run
├── results/
│   └── eval-data.json          # Normalized aggregate and task-level results
└── tasks/<task>/
    ├── instruction.md          # Prompt shown to every harness
    └── task.toml               # Public task metadata and environment definition
```

The repository intentionally contains **results and task definitions only**. Internal infrastructure, credentials, runtime identifiers, private evidence, solutions, and deployment configuration are not included.

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

<div align="center"><img src="assets/divider.svg" width="100%" height="1" alt="" /></div>

- FrontierHarness v1.0 focuses on software engineering contexts and terminal-based tasks. It may not generalize to other areas of knowledge work.
- Evaluated on Runta agent runtimes. For each task, all harnesses and the environment defined in `task.toml` are prepared once as a golden checkpoint. Every run is a fresh restore with identical vCPU, memory, disk size, disk contents, and memory state.
- Kimi K3 is served by [Fireworks](https://fireworks.ai/).

### Benchmark scope

- **30 tasks:** 21 Terminal-Bench tasks and 9 DeepSWE tasks
- **9 harnesses:** Claude Code, Codex, DeepSeek Harness, Exo Harness, Hermes, Kimi Code, Oh My Pi, OpenCode, and Pi
- **12 configurations:** one canonical result for every task and harness-configuration pair
- **360 evaluations:** complete task-by-harness coverage
- **Deterministic scoring:** verifier-based pass/fail outcomes
- **Comparable cost:** first-turn cache reads repriced consistently across harnesses

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
  <a href="https://runta.com"><img src="assets/runta-sponsor.svg" width="330" alt="Sponsored by Runta" /></a>
</p>
