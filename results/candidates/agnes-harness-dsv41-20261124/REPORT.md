# FrontierHarness Eval v1.1 — Agnes Harness + DeepSeek-V4.1-Flash-1017

## Summary
- **Dataset**: `frontier-harness-eval/frontier-harness-eval@v1.1.0` (62 tasks × 4 attempts = 248 trials)
- **Harness**: Agnes Harness (`agnes-cli` via `harbor_agh_agent:AgnesHarnessAgent`)
- **Model**: `deepseek-v4.1-flash-1017`
- **Timeout Multiplier**: `1.0`
- **Overall Pass Rate (248 trials)**: **60.89%** (`151 / 248`)
- **Pass@4 (at least 1/4)**: **69.35%** (`43 / 62` tasks)
- **4/4 All-Pass Tasks**: `30 / 62`
- **1–3/4 Partial-Pass Tasks**: `13 / 62`
- **0/4 Tasks**: `19 / 62`
- **Avg Duration / Trial**: `596.95s` (`41.12` total trial-hours)
- **Total Tokens**: `22,970,955` input / `10,645,587` output
- **Infrastructure Exceptions**: `0` (`11` `AgentTimeoutError` task timeouts scored as failures; `1` pre-`docker-buildx` `RuntimeError` on `batched-eval-parity__GwBbjmM` was excluded and rerun cleanly in `fhe-v11-batched-eval-parity-rerun1`).

## Measurement Boundaries
1. **Execution environment**: Executed via `harbor==0.26.0` using local Docker containers on a dedicated Ubuntu 26.04 host (`8 vCPU`, `30 GiB RAM`, `docker-buildx`) rather than Runta cloud sandboxes. Submitted as an unranked candidate under `results/candidates/agnes-harness-dsv41-20261124/`.
2. **Model endpoint**: `deepseek-v4.1-flash-1017` served via OpenAI-compatible proxy (`agrouter-ng-test.kiwiar.com/v1`), which does not emit `cost_usd` in `agent_result` (token counts are fully recorded).
3. **Fairness & parameters**: `--timeout-multiplier 1.0`, `--max-turns 100`, `--permission full-access`, no task or verifier modifications.
