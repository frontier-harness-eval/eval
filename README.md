<p align="center">
  <a href="https://eval.runta.com">
    <img src="https://eval.runta.com/runta-logo.png" width="72" alt="Runta" />
  </a>
</p>

<h1 align="center">Runta Eval</h1>

<p align="center">
  <strong>One model. Twelve harnesses. Thirty real agentic tasks.</strong>
</p>

<p align="center">
  <a href="https://eval.runta.com"><img alt="Interactive leaderboard" src="https://img.shields.io/badge/interactive-leaderboard-ff6e1a?style=flat-square" /></a>
  <img alt="Kimi K3" src="https://img.shields.io/badge/model-Kimi_K3-5019c5?style=flat-square" />
  <img alt="360 runs" src="https://img.shields.io/badge/evaluations-360-222?style=flat-square" />
  <img alt="30 tasks" src="https://img.shields.io/badge/tasks-30-222?style=flat-square" />
  <img alt="12 harnesses" src="https://img.shields.io/badge/harnesses-12-222?style=flat-square" />
</p>

<p align="center">
  <a href="https://eval.runta.com"><strong>Explore the live results →</strong></a>
</p>

---

## Same model. Different harness. Very different outcome.

We ran the same **Kimi K3** model through 12 coding-agent harnesses on the same 30-task benchmark. The harness alone changed task success, cost, cache behavior, and time.

| Harness | Tasks passed | Median cost per successful task | Median time per successful task |
|---|---:|---:|---:|
| **Codex** | **20 / 30** | $0.1243 | 6m 43s |
| DSH Creator | 19 / 30 | $0.1194 | 6m 44s |
| Claude Code | 19 / 30 | $0.2880 | 9m 38s |
| Pi | 18 / 30 | $0.0709 | 7m 33s |
| DSH Standard | 18 / 30 | $0.1201 | 6m 17s |
| DSH PTC | 18 / 30 | $0.1370 | 7m 44s |
| Kimi Code | 17 / 30 | $0.1818 | 7m 56s |
| DSH Minimal | 17 / 30 | $0.1214 | **5m 41s** |
| Oh My Pi | 17 / 30 | $0.1354 | 6m 46s |
| Exo Harness | 16 / 30 | $0.0748 | 6m 17s |
| Hermes | 15 / 30 | $0.1746 | 6m 58s |
| OpenCode | 15 / 30 | **$0.0615** | 6m 27s |

> The leaderboard is only the start. Failed runs, total cost per pass, cache behavior, and task-level results are available in the [interactive report](https://eval.runta.com).

## What is in this repository

```text
.
├── benchmark.json              # Public benchmark definition
├── metadata/
│   ├── difficulty.json         # Difficulty assignments and source methodology
│   └── harness-versions.json   # Harness versions used for the run
├── results/
│   ├── eval-data.json          # Normalized aggregate and task-level results
│   └── scatter-data.json       # Pareto chart coordinates and frontier data
└── tasks/<task>/
    ├── instruction.md          # Prompt shown to every harness
    └── task.toml               # Public task metadata and environment definition
```

The repository intentionally contains **results and task definitions only**. Internal infrastructure, credentials, runtime identifiers, private evidence, solutions, and deployment configuration are not included.

## Benchmark design

- **30 tasks:** 21 Terminal-Bench tasks and 9 DeepSWE tasks
- **12 harnesses:** Claude Code, Codex, four DSH modes, Exo Harness, Hermes, Kimi Code, Oh My Pi, OpenCode, and Pi
- **One model:** Kimi K3, served by Fireworks
- **360 cells:** one canonical result for every task × harness pair
- **Deterministic scoring:** verifier-based pass/fail outcomes
- **Comparable cost:** first-turn cache reads repriced consistently across harnesses

See [`benchmark.json`](benchmark.json) for the public benchmark definition and [`results/eval-data.json`](results/eval-data.json) for the complete normalized result set.

## Use the data

```bash
jq '.harnesses[] | {name, successful, effective_cost_per_pass}' results/eval-data.json
```

Every task directory contains the exact public instruction and task metadata used by the benchmark.

---

<div align="center">

## Build and run your agents on Runta

Runta gives agents secure execution, governed access, secret protection, and the infrastructure to run real workloads at scale.

### [Start free trial →](https://dashboard.runta.com)

[Explore Runta](https://runta.com) · [Talk to the Runta team](https://dashboard.runta.com/request-demo) · [View the live eval](https://eval.runta.com)

</div>
