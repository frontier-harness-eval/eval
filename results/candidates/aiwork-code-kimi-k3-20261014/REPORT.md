# AiWork.Code on Kimi K3

**Organization:** Ant Digital Technologies

**Result: 30/30 tasks completed; 25 passed, 5 failed (83.3%). Unranked.**

> **Selection disclosure — this is not a first-valid-attempt result.** `benchmark.json` sets
> `canonical_selection` to the first valid attempt. Between 2026-09-21 and 2026-10-18 our
> evaluation gateway ran **37 complete 30-task sweeps** of AiWork.Code development builds on this
> task set (36 via our internal model gateway, one via Kimi's official API). Four scored 0/30; the other 33 scored
> **15–25 passes (median 20)**. This run is the **single highest-scoring sweep**, chosen after
> the fact; the next highest is 24/30. Its build was swept once; two sibling builds of the same
> version scored 21/30 and 22/30, and a fixed reference build swept 11 times scored 19–23
> (median 20). Treat 25/30 as an upper-end sample, not an expected score. Every sweep, and the
> partial and smoke runs, are listed in [TRACES.md](TRACES.md).

> **Harness modifications.** The adapters (published in [`adapter/`](adapter/)) append a short
> block of operating rules to every task instruction, preload uv and a standalone Python into
> every task container, and, for Terminal-Bench only, pin the model host in `/etc/hosts`. The
> exact rules text is in `run-config.json` → `harness_modifications`.

This is a local-Docker run (no Runta golden checkpoint), submitted for maintainer inspection and
reproduction — not a claim of an official leaderboard placement. `methodology_comparable = false`.

| Suite | Completed | Passed | Tasks with usage | Cost, first-call-cold |
|---|---:|---:|---:|---:|
| Terminal-Bench | 21/21 | 17 | 19/21 | ≥ $12.90 |
| DeepSWE | 9/9 | 8 | 9/9 | $59.33 |
| **All** | **30/30** | **25** | **28/30** | **≥ $72.23** |

Cost per pass is **$2.89 or more**: two failures were killed at
the agent timeout before their usage was persisted, so the totals are lower bounds. Median task
duration is 9m 08s over all 30 tasks. Over the 25 passes: median
duration 4m 22s, median cost $0.66,
typical cache hit rate 77.0% (25/25 measured), mean
turns 42.9. Infra-invalid: 0.

## Reproduction and evidence

- `run-config.json` pins the launch bundle: binary-only `dtcoder v1.26423.0-c9b4e7d`, sha256
  `ae33d1f2…96524bba`, matching `agent_info.version` in all 30 run-leaf `result.json` files.
  The binary is not publicly downloadable; it is available to maintainers on request.
- [`adapter/`](adapter/) holds the Harbor and Pier adapters this run used (sha256 `93712292…`
  and `e97a0e6f…`; the published copies have the gateway host and IPs redacted, see the adapter README). They are not the adapters proposed in #24; #24 was not used here. The
  gateway runner that launched the jobs is not published; what it set is listed in
  `run-config.json` (`topology`, `runtime_egress_policy`).
- `observed-results.json` has per-task outcome, native verifier reward, duration, token usage,
  repriced cost, and the SHA256 digest of each task's evidence directory.
- The release tarball linked from [TRACES.md](TRACES.md) has, for all 30 tasks, the agent's
  stream-json (streamed reasoning and text, tool calls and results, per-call usage), verifier
  output, Harbor/Pier job configs, locks and logs, and the gateway's original aggregate, with a
  per-file manifest and checksums. dtcoder's per-round request/response capture is omitted, so
  system prompts and tool schemas are not included.
- Costs are the FHE price-table repricing (`kimi-k3-2026-08-20`) on the first-call-cold basis,
  not provider billing. Missing usage is excluded, never zero-filled.

## Configuration and deviations

- Kimi K3 served by our **internal model gateway** over the **anthropic-messages**
  wire, not Fireworks. `dtcoder __print … -y --thinking-level high`, one run per task.
- Local Docker on one host. The gateway ran **8 tasks in parallel**, each as its own Harbor or
  Pier job. No Runta checkpoint or fresh restore; no matched control run.
- Native timeouts kept (`timeout_multiplier` 1.0, no overrides; DeepSWE 5400 s).
- Terminal-Bench: `terminal-bench@2.0` at `69671fba…`, `environment_mode=shared` (the verifier
  runs in the agent's container), public network. The agent's outbound HTTP(S) goes through a
  transport proxy except hosts on `NO_PROXY` (the model host, two other model APIs, three mirror
  hosts, and corporate domains). The verifier's dependency installs use PyPI, Hugging Face, and
  GitHub mirrors; the preloaded Python is visible in at least one
  Terminal-Bench verifier's output (gcode-to-text).
- DeepSWE: air-gapped by Pier's per-task squid except the model host; the agent reaches the
  model through Pier's own squid proxy. Verifiers run in a separate image, so the uv/Python
  preload reaches only the agent container. The local corpus is not a
  git checkout; images are referenced by tag, and three tags (expr, httpx, python-statemachine)
  carry a `-v1.1` suffix not in the frozen `task.toml`.
- One repetition per task, no retries. The provider reported no cache-write tokens on this wire;
  fresh-input and cache-write share the $3/Mtok rate, so cost is unaffected.

## Failures inspected

- **build-cython-ext**: the verifier passed 11/11 (reward 1.0), but the agent was killed at the
  task's 900 s agent timeout before its usage was persisted. FHE scoring counts a pass only with
  reward ≥ 1 and observed usage, so it is a failure.
- **extract-elf**: 1/2 tests; the output matched 0% of the reference values (75% required).
- **gcode-to-text**: killed at the 900 s agent timeout before writing `/app/out.txt`; 0/2
  tests; no usage persisted.
- **polyglot-c-py**: a compiled `cmain` was left next to `main.py.c` in a directory that must
  contain only `main.py.c`; 0/1.
- **Meriyah**: P2P 51,469/51,469, F2P 48/49; `using` with `of` as the binding name in a for-of
  loop failed.

## Tasks

Cost is first-call-cold repriced USD; "—" means no usage was persisted.

| Task | Verifier reward | Scored | Cost | Time | Turns |
|---|---:|---|---:|---:|---:|
| terminal-bench/regex-log | 1 | pass | $0.71 | 9m 54s | 18 |
| terminal-bench/build-cython-ext | 1 | **fail** | — | 15m 46s | — |
| terminal-bench/chess-best-move | 1 | pass | $0.65 | 4m 02s | 14 |
| terminal-bench/code-from-image | 1 | pass | $0.41 | 1m 41s | 8 |
| terminal-bench/constraints-scheduling | 1 | pass | $0.47 | 3m 43s | 9 |
| terminal-bench/db-wal-recovery | 1 | pass | $0.54 | 3m 23s | 12 |
| terminal-bench/dna-insert | 1 | pass | $1.31 | 15m 28s | 28 |
| terminal-bench/extract-elf | 0 | **fail** | $1.25 | 13m 45s | 29 |
| terminal-bench/gcode-to-text | 0 | **fail** | — | 16m 00s | — |
| terminal-bench/git-leak-recovery | 1 | pass | $0.51 | 2m 19s | 10 |
| terminal-bench/kv-store-grpc | 1 | pass | $0.61 | 2m 05s | 14 |
| terminal-bench/largest-eigenval | 1 | pass | $1.08 | 9m 32s | 29 |
| terminal-bench/log-summary-date-ranges | 1 | pass | $0.66 | 2m 29s | 14 |
| terminal-bench/merge-diff-arc-agi-task | 1 | pass | $0.88 | 6m 42s | 27 |
| terminal-bench/modernize-scientific-stack | 1 | pass | $0.42 | 1m 58s | 8 |
| terminal-bench/multi-source-data-merger | 1 | pass | $0.49 | 2m 46s | 9 |
| terminal-bench/openssl-selfsigned-cert | 1 | pass | $0.66 | 2m 44s | 13 |
| terminal-bench/polyglot-c-py | 0 | **fail** | $0.57 | 8m 45s | 14 |
| terminal-bench/sanitize-git-repo | 1 | pass | $0.56 | 4m 12s | 16 |
| terminal-bench/sqlite-db-truncate | 1 | pass | $0.47 | 4m 22s | 9 |
| terminal-bench/vulnerable-secret | 1 | pass | $0.64 | 2m 59s | 16 |
| datacurve/anko-typed-variable-bindings | 1 | pass | $3.06 | 23m 37s | 60 |
| datacurve/arktype-json-schema-refs-dependencies | 1 | pass | $11.71 | 69m 23s | 169 |
| datacurve/expr-try-catch-errors | 1 | pass | $6.83 | 47m 42s | 100 |
| datacurve/fastapi-deprecation-response-headers | 1 | pass | $2.52 | 24m 28s | 54 |
| datacurve/httpx-multipart-response-parsing | 1 | pass | $3.05 | 27m 29s | 61 |
| datacurve/katex-multicolumn-array-spans | 1 | pass | $6.90 | 45m 54s | 115 |
| datacurve/meriyah-explicit-resource-declarations | 0 | **fail** | $6.83 | 48m 03s | 117 |
| datacurve/python-statemachine-state-data-scoping | 1 | pass | $12.55 | 62m 18s | 165 |
| datacurve/scc-bounded-memory-spilling | 1 | pass | $5.88 | 35m 18s | 94 |
