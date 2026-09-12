# Alma on FrontierHarness Eval

![Pass rate versus median cost per task, Alma against the FrontierHarness Eval baselines](chart.svg)

## Result

| Metric | Value |
| --- | --- |
| Pass rate | 83.3% |
| Tasks passed | 25 / 30 |
| Cost per pass | $2.40 |
| Complete cost coverage | 30/30 tasks |
| Median cost per successful task | $0.31 (25/25 successes measured) |
| Median time per successful task | 4m 32s |
| Median cache hit rate | 89.7% |
| Cache measurement coverage | 25/25 successful tasks with measured cache rates |
| Mean turns | 39.8 |

## Comparison

| # | Harness | Pass rate | Median cost per task | Cache, median | Median time |
| --- | --- | --- | --- | --- | --- |
| 01 | Codex | 66.7% | $3.47 | 88.0% | 6m 43s |
| 02 | Claude Code | 63.3% | $18.34 | 67.8% | 9m 38s |
| 03 | DSH Creator | 63.3% | $3.28 | 84.3% | 6m 44s |
| 04 | DSH PTC | 60.0% | $4.58 | 87.2% | 7m 44s |
| 05 | DSH Standard | 60.0% | $3.46 | 86.5% | 6m 17s |
| 06 | Pi | 60.0% | $2.43 | 79.4% | 7m 33s |
| 07 | DSH Minimal | 56.7% | $4.72 | 84.6% | 5m 41s |
| 08 | Kimi Code | 56.7% | $3.65 | 88.0% | 7m 56s |
| 09 | Oh My Pi | 56.7% | $4.75 | 82.2% | 6m 46s |
| 10 | Exo Harness | 53.3% | $1.05 | 70.3% | 6m 17s |
| 11 | Hermes | 50.0% | $2.90 | 85.9% | 6m 58s |
| 12 | OpenCode | 50.0% | $3.24 | 78.4% | 6m 27s |
| — | **Alma** | 83.3% | $2.40 | 89.7% | 4m 32s |

## Reproducibility

| Field | Value |
| --- | --- |
| Run id | `alma-full-20260911-2300` |
| Golden checkpoint | `alma-golden-v10` |
| Model | `fireworks_ai/accounts/fireworks/models/kimi-k3` |
| Provider | `fireworks` |
| Harness repo | `https://github.com/yetone/alma` |
| Harness commit | `a26dd7b4858c33db4d48d0eed271f163d919b444` |
| Runtime | 4 vCPU, 8192 MiB |
| Harbor | `0.22.0` |
| Pier | `0.3.1` |
| DeepSWE corpus | `435ee89ec2f2e2289f33b0da4f992f0b7b7266b9` |
| Started | 2026-09-11T15:02:15Z |


## Task results

| Task | Result | Cost | Time | Turns | Cache hit rate | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `datacurve/anko-typed-variable-bindings` | pass | $2.96 | 21m 50s | 85 | 98.3% | [evidence](../trials/datacurve-anko-typed-variable-bindings) |
| `datacurve/arktype-json-schema-refs-dependencies` | pass | $7.97 | 55m 30s | 148 | 98.9% | [evidence](../trials/datacurve-arktype-json-schema-refs-dependencies) |
| `datacurve/expr-try-catch-errors` | pass | $5.07 | 33m 3s | 107 | 98.6% | [evidence](../trials/datacurve-expr-try-catch-errors) |
| `datacurve/fastapi-deprecation-response-headers` | pass | $2.52 | 20m 19s | 81 | 98.2% | [evidence](../trials/datacurve-fastapi-deprecation-response-headers) |
| `datacurve/httpx-multipart-response-parsing` | pass | $1.87 | 16m 16s | 55 | 97.4% | [evidence](../trials/datacurve-httpx-multipart-response-parsing) |
| `datacurve/katex-multicolumn-array-spans` | pass | $4.38 | 29m 16s | 107 | 98.6% | [evidence](../trials/datacurve-katex-multicolumn-array-spans) |
| `datacurve/meriyah-explicit-resource-declarations` | failure | $9.42 | 53m 49s | 160 | 99.0% | [evidence](../trials/datacurve-meriyah-explicit-resource-declarations) |
| `datacurve/python-statemachine-state-data-scoping` | pass | $5.92 | 33m 39s | 133 | 98.9% | [evidence](../trials/datacurve-python-statemachine-state-data-scoping) |
| `datacurve/scc-bounded-memory-spilling` | ★ Solved · 0/12 baselines passed | $3.71 | **26m 37s** | 86 | 98.3% | [evidence](../trials/datacurve-scc-bounded-memory-spilling) |
| `terminal-bench/build-cython-ext` | pass | $0.54 | 6m 10s | 40 | 96.2% | [evidence](../trials/terminal-bench-build-cython-ext) |
| `terminal-bench/chess-best-move` | failure | $3.17 | 16m 27s | 24 | 92.0% | [evidence](../trials/terminal-bench-chess-best-move) |
| `terminal-bench/code-from-image` | failure | $7.99 | 20m 34s | 52 | 95.0% | [evidence](../trials/terminal-bench-code-from-image) |
| `terminal-bench/constraints-scheduling` | pass | $0.20 | 2m 48s | 7 | 83.0% | [evidence](../trials/terminal-bench-constraints-scheduling) |
| `terminal-bench/db-wal-recovery` | pass | $0.11 | 1m 50s | 7 | 83.3% | [evidence](../trials/terminal-bench-db-wal-recovery) |
| `terminal-bench/dna-insert` | pass | $0.49 | 6m 47s | 18 | 89.7% | [evidence](../trials/terminal-bench-dna-insert) |
| `terminal-bench/extract-elf` | pass | $0.40 | 4m 54s | 15 | 89.4% | [evidence](../trials/terminal-bench-extract-elf) |
| `terminal-bench/gcode-to-text` | failure | $0.78 | 3m 6s | 13 | 76.3% | [evidence](../trials/terminal-bench-gcode-to-text) |
| `terminal-bench/git-leak-recovery` | pass | $0.09 | 1m 24s | 7 | 83.9% | [evidence](../trials/terminal-bench-git-leak-recovery) |
| `terminal-bench/kv-store-grpc` | ★ Solved · 0/12 baselines passed | $0.10 | **1m 42s** | 8 | 86.3% | [evidence](../trials/terminal-bench-kv-store-grpc) |
| `terminal-bench/largest-eigenval` | ★ Solved · 0/12 baselines passed | $0.17 | **2m 19s** | 10 | 88.0% | [evidence](../trials/terminal-bench-largest-eigenval) |
| `terminal-bench/log-summary-date-ranges` | pass | $0.07 | 1m 4s | 4 | 73.1% | [evidence](../trials/terminal-bench-log-summary-date-ranges) |
| `terminal-bench/merge-diff-arc-agi-task` | pass | $0.21 | 3m 6s | 16 | 91.9% | [evidence](../trials/terminal-bench-merge-diff-arc-agi-task) |
| `terminal-bench/modernize-scientific-stack` | pass | $0.07 | 1m 8s | 4 | 73.0% | [evidence](../trials/terminal-bench-modernize-scientific-stack) |
| `terminal-bench/multi-source-data-merger` | pass | $0.11 | 1m 29s | 6 | 80.7% | [evidence](../trials/terminal-bench-multi-source-data-merger) |
| `terminal-bench/openssl-selfsigned-cert` | pass | $0.09 | 1m 11s | 6 | 81.7% | [evidence](../trials/terminal-bench-openssl-selfsigned-cert) |
| `terminal-bench/polyglot-c-py` | pass | $0.44 | 6m 16s | 14 | 91.9% | [evidence](../trials/terminal-bench-polyglot-c-py) |
| `terminal-bench/regex-log` | pass | $0.31 | 4m 32s | 9 | 86.1% | [evidence](../trials/terminal-bench-regex-log) |
| `terminal-bench/sanitize-git-repo` | failure | $0.52 | 7m 45s | 21 | 92.7% | [evidence](../trials/terminal-bench-sanitize-git-repo) |
| `terminal-bench/sqlite-db-truncate` | pass | $0.14 | 1m 43s | 7 | 82.8% | [evidence](../trials/terminal-bench-sqlite-db-truncate) |
| `terminal-bench/vulnerable-secret` | pass | $0.17 | 1m 30s | 15 | 91.5% | [evidence](../trials/terminal-bench-vulnerable-secret) |


---

Baseline data and methodology: [FrontierHarness Eval](https://frontierharness.org/)
