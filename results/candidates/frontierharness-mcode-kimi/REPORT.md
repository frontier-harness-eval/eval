# mcode (MiniMax Code) on FrontierHarness Eval — candidate result

**76.7% pass rate (23/30)**, scored strictly by the official verifiers. This is a third-party candidate result submitted for reproduction and verification; the comparison below is a numerical ordering of recorded pass rates, not an official leaderboard placement.

- Median time per successful task: **4m 33s**
- Run id: `frontierharness-mcode-kimi` · started `2026-09-07T04:00:03Z`
- Harness: `mcode` (MiniMax Code) `0.3.2`, driven through the Harbor adapter from PR #2
- Model: Kimi K3 (`openai/kimi-k3`), thinking=max, max output 131072, context 1048576, default sampling; prompt compression and X-Ray disabled

## Result

| Metric | Value |
| --- | --- |
| Pass rate | 76.7% (23/30) |
| Failed | 4 |
| Timed out before verifier scoring | 3 (counted in the 30-attempt denominator) |
| `infra_invalid` | 0 |
| Median time per successful task | 4m 33s |
| Effective cost per pass (USD) | n/a — see cost note |

The three timeouts (`arktype-json-schema-refs-dependencies`, `meriyah-explicit-resource-declarations`, `python-statemachine-state-data-scoping`) hit the 5400s task limit before the verifier ran. They received no verifier score and are counted against the pass rate, so 76.7% is the conservative reading; the pass rate over verifier-scored attempts is 23/27.

## Cost note

The official USD cost fields are left empty rather than estimated: this run served Kimi K3 through Moonshot's official CN API (`api.moonshot.cn`) instead of Fireworks, and the `*_normalized` cache repricing inputs are not public. Raw usage-based CNY estimates per task are in [`model-costs-cny.csv`](model-costs-cny.csv) (total ≈ ¥279.85 across all 30 attempts, including failures; usage not returned after aborts is still pending, not zero). Pass rate remains comparable because the model is identical; do not compare the CNY figures against the published USD `effective_cost_per_pass` without checking token prices.

## Invariants held / relaxed

Held:

- Kimi K3 for every task; no other model involved.
- One golden checkpoint, one fresh restore per task, identical requested resources (4 vCPU / 8192 MiB).
- No formal task executed before either checkpoint was frozen.
- Official task definitions, verifiers, and native task time limits unmodified.
- No task re-runs or best-of-N; every task was attempted exactly once.
- Zero trials marked `infra_invalid`.

Relaxed / disclosed:

- **Provider**: Moonshot official CN API rather than Fireworks. Affects cost accounting and latency, not verifier scoring.
- **Checkpoint rebuild mid-run**: a Runta infrastructure issue before case 9 required rebuilding the checkpoint following Runta's guidance. Evaluation code, task images, Python dependencies, and model configuration were kept identical; the underlying Runta image's system runc moved from 1.4.3 to 1.5.1, so the two checkpoints are not byte-identical. Tasks 1–8 ran on `01a079eb-fde2-7553-8d91-5c47fc642de5`, tasks 9–30 on `01a07c81-d5e9-7dce-8b67-e03c2bae8bcb`. No checkpoint-restore fault recurred after the rebuild.
- **Shared checkpoint layout**: this run used one shared checkpoint with all task images pre-pulled (per the third-party skill), while the published 360 baseline runs used per-task checkpoints.
- **DeepSWE task limit**: task files in this run specify 5400s; some public per-task records for the same tasks show attempts ending at 3600s, so exact parity of that limit is not confirmed.

## Files

| File | Content |
| --- | --- |
| [`candidate.json`](candidate.json) | Output of the official `normalize-results.mjs` scoring |
| [`run-config.json`](run-config.json) | Run metadata: command template, timeout, egress allowlist (one internal telemetry host redacted), per-task images and limits |
| [`trials/<task>/trial.json`](trials/) | Official per-trial summaries (status, duration, exit code, checkpoint) |
| [`model-costs-cny.csv`](model-costs-cny.csv) | Per-task status, durations, and raw-usage CNY cost estimates |
| [`report/chart.svg`](report/chart.svg) | Chart from the official `generate-chart.mjs` |

Full raw evidence (30 per-task bundles with complete agent trajectories, tool calls, usage, verifier stdout, and collected `model.patch`) is preserved offline — roughly 150 MB of archives that do not belong in this repository. We will provide it to the maintainers on request for reproduction and verification.

## Failed-task detail

| Task | Verifier outcome |
| --- | --- |
| `datacurve/expr-try-catch-errors` | 73/79 fail-to-pass tests passed (p2p 66265/66265); 6 new tests failed on error-text/error-type edge semantics |
| `terminal-bench/build-cython-ext` | Hit the 900s task limit; verifier ran with one remaining `KeyError: 'pos'` compatibility failure (10/11 verifier tests passed) |
| `terminal-bench/dna-insert` | Forward/reverse primer melting temperatures differ by more than the required 5°C |
| `terminal-bench/polyglot-c-py` | A self-test binary (`cmain`) was left in the target directory, violating the single-file requirement |
