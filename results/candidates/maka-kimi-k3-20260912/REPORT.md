# Maka on Kimi K3

**Draft result: 30/30 tasks completed; 23 passed, 7 failed.**

This is the first full formal sweep under the frozen configuration. Results are unranked and submitted for inspection, not an official leaderboard placement. Final accounting and normalized report artifacts are being completed.

| Suite | Completed | Passed |
|---|---:|---:|
| Terminal-Bench | 21/21 | 18 |
| DeepSWE | 9/9 | 5 |

## Reproduction and evidence

- The exact Maka source commit is linked in `run-config.json`; this evaluates a development branch, not a released Maka version.
- `observed-results.json` contains per-task native outcomes, subject execution duration, captured usage, cost, and SHA256 digests of retained full evidence archives. Absolute local paths, credentials, prompts, solutions, and infrastructure identifiers are excluded.
- Full per-task archives retain native verifier output, Runtime Host trajectories, outbound requests, and provider usage locally. They are not included here because they require separate redaction before sharing.
- Accounting is observed provider-token pricing, not first-call-cold normalized benchmark pricing. Aggregate interrupted-call billing adjustments are separate and do not fabricate missing tokens. Do not use these costs as a normalized leaderboard comparison. The normalized candidate/report remains pending.

## Configuration and deviations

- Fireworks Kimi K3; Maka headless-coding-v1 prompt and ArchiveRead/Bash/Edit/Glob/Grep/Read/Write tools. Named sessions suppress title generation.
- Reasoning effort omitted (provider default Max at preflight); no output-limit or prompt-truncation override; maxSteps 1,000,000. Native task timeouts retained.
- One shared clean checkpoint, fresh restore per task, 4 vCPU / 8 GiB RAM / 50 GiB disk, serial execution, task images pulled after restore. A single hash-verified launch bundle is installed before each task.
- Custom Runtime Host relay and budget proxy rather than the stock CLI runner. Shared recorded package/source allowlist; Fireworks inference metered; HTTP/2 disabled after preflight transport failures. Pier uses its authenticated proxy and CA forwarding.
- Historical baselines did not retain the applied egress allowlist and used different checkpoint arrangements. No matched paid control was run. Environment equivalence is not established.
- Earlier certificate/regex smoke runs and a network-blocked build-cython attempt are disclosed. Infra-invalid preflight attempts are excluded from this formal cohort, with all costs and evidence retained separately.
- No valid formal model attempt was rerun. Tasks 2 and 8 required read-only controller recovery after completion, without restarting the agent. Task 12 hit its native 900-second deadline and remains a failure.

## Failures inspected

- dna-insert: primer melting-temperature difference exceeded the verifier limit.
- largest-eigenval: native 900-second agent timeout; final request usage missing, aggregate billing adjustment $0.039315.
- polyglot-c-py: compiled cmain artifact remained in a directory required to contain only main.py.c.
- Anko: P2P 94/94, F2P 1/9; new vm test suite build failed. Retained output does not establish the precise compiler error.
- Expr: P2P 66,265/66,265, F2P 78/79; error type expected type but returned custom.
- Meriyah: P2P 51,469/51,469, F2P 47/49; using in switch cases and of as a for-of binding name failed.

## Tasks

| Task | Native score | Status |
|---|---:|---|
| terminal-bench/regex-log | 1 | completed |
| terminal-bench/build-cython-ext | 1 | completed |
| terminal-bench/chess-best-move | 1 | completed |
| terminal-bench/code-from-image | 1 | completed |
| terminal-bench/constraints-scheduling | 1 | completed |
| terminal-bench/db-wal-recovery | 1 | completed |
| terminal-bench/dna-insert | 0 | completed |
| terminal-bench/extract-elf | 1 | completed |
| terminal-bench/gcode-to-text | 1 | completed |
| terminal-bench/git-leak-recovery | 1 | completed |
| terminal-bench/kv-store-grpc | 1 | completed |
| terminal-bench/largest-eigenval | 0 | subject_failed |
| terminal-bench/log-summary-date-ranges | 1 | completed |
| terminal-bench/merge-diff-arc-agi-task | 1 | completed |
| terminal-bench/modernize-scientific-stack | 1 | completed |
| terminal-bench/multi-source-data-merger | 1 | completed |
| terminal-bench/openssl-selfsigned-cert | 1 | completed |
| terminal-bench/polyglot-c-py | 0 | completed |
| terminal-bench/sanitize-git-repo | 1 | completed |
| terminal-bench/sqlite-db-truncate | 1 | completed |
| terminal-bench/vulnerable-secret | 1 | completed |
| datacurve/anko-typed-variable-bindings | 0 | completed |
| datacurve/arktype-json-schema-refs-dependencies | 1 | completed |
| datacurve/expr-try-catch-errors | 0 | completed |
| datacurve/fastapi-deprecation-response-headers | 1 | completed |
| datacurve/httpx-multipart-response-parsing | 1 | completed |
| datacurve/katex-multicolumn-array-spans | 1 | completed |
| datacurve/meriyah-explicit-resource-declarations | 0 | completed |
| datacurve/python-statemachine-state-data-scoping | 1 | completed |
| datacurve/scc-bounded-memory-spilling | 0 | completed |

SCC: P2P 286/286, F2P 28/31; three csv-stream format/output equivalence tests failed.
