# mcode (MiniMax Code) on FrontierHarness Eval — candidate result

**76.7% pass rate (23/30)**, scored strictly by the official verifiers. This is a third-party candidate result submitted for reproduction and verification; the comparison below is a numerical ordering of recorded pass rates, not an official leaderboard placement.

- Median time per successful task: **4m 33s**
- Run id: `frontierharness-mcode-kimi` · started `2026-09-07T04:00:03Z`
- Harness: `mcode` (MiniMax Code) `0.3.2`, driven headless through a pinned Harbor adapter
- Model: Kimi K3 (`openai/kimi-k3`), thinking=max, max output 131072, context 1048576, default sampling; prompt compression and X-Ray disabled

## Result

| Metric | Value |
| --- | --- |
| Pass rate | 76.7% (23/30) |
| Failed | 4 |
| Timed out before verifier scoring | 3 (counted in the 30-attempt denominator) |
| `infra_invalid` | 0 |
| Median time per successful task | 4m 33s |
| Effective cost per pass (USD, repriced at the baseline card) | **$1.83** — lower bound, see cost note |

The three timeouts (`arktype-json-schema-refs-dependencies`, `meriyah-explicit-resource-declarations`, `python-statemachine-state-data-scoping`) hit the 5400s task limit before the verifier ran. They received no verifier score and are counted against the pass rate, so 76.7% is the conservative reading; the pass rate over verifier-scored attempts is 23/27.

## Cost note

This run served Kimi K3 through Moonshot's official CN API (`api.moonshot.cn`), billed in CNY, so the official USD cost fields in `candidate.json` are left as `normalize-results.mjs` produced them (empty) rather than hand-filled.

The cost is still computable in the baseline's own terms. Per `reference.md`, Moonshot's list price matches the baseline card used by the Fireworks/OpenRouter/Together baselines ($3.00 per million input tokens, $0.30 per million cached input tokens, $15.00 per million output tokens). Repricing this run's raw per-task token usage at exactly that card gives:

- **Total model cost: $41.98** across all 30 attempts (failures included)
- **Effective cost per pass: $41.98 / 23 = $1.83**
- Median cost per successful task: $0.18

Two caveats, both in the conservative direction or disclosed:

1. **Lower bound**: 4 tasks (`arktype-json-schema-refs-dependencies`, `meriyah-explicit-resource-declarations`, `python-statemachine-state-data-scoping`, `build-cython-ext`) have partial usage — the final in-flight request's usage was not returned after the timeout abort — so their true cost is slightly higher than recorded.
2. **Cache behaviour is provider-dependent** (minimum prefix length, TTL), as `reference.md` notes. The cache hit rates in this run (median ≈ 89%) were produced by Moonshot's serving; the same trajectories on Fireworks could price slightly differently. The `*_normalized` baseline fields that reprice first-turn cache reads use non-public inputs and are left empty.

Per-task figures in both currencies are in [`model-costs.csv`](model-costs.csv): `model_cost_cny_estimate` is the raw-usage CNY estimate on Moonshot pricing (total ≈ ¥279.85), and `model_cost_at_baseline_prices_usd` is the same token usage repriced at the baseline card.

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
| [`model-costs.csv`](model-costs.csv) | Per-task status, durations, raw-usage CNY estimates, and USD repriced at the baseline card |
| [`report/chart.svg`](report/chart.svg) | Chart from the official `generate-chart.mjs`; generated with mcode's cost repriced at the baseline card ($1.83 per pass); the repricing footnote and axis wording were adjusted post-generation |

Full raw evidence (30 per-task bundles with complete agent trajectories, tool calls, usage, verifier stdout, and collected `model.patch`) is preserved offline — roughly 150 MB of archives that do not belong in this repository. We will provide it to the maintainers on request for reproduction and verification.

## Failed-task detail

| Task | Verifier outcome |
| --- | --- |
| `datacurve/expr-try-catch-errors` | 73/79 fail-to-pass tests passed (p2p 66265/66265); 6 new tests failed on error-text/error-type edge semantics |
| `terminal-bench/build-cython-ext` | Hit the 900s task limit; verifier ran with one remaining `KeyError: 'pos'` compatibility failure (10/11 verifier tests passed) |
| `terminal-bench/dna-insert` | Forward/reverse primer melting temperatures differ by more than the required 5°C |
| `terminal-bench/polyglot-c-py` | A self-test binary (`cmain`) was left in the target directory, violating the single-file requirement |
