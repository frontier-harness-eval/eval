# Agent Core on FrontierHarness v1.1

This document records the evaluated configuration and how to launch the same one-attempt matrix on Runta. The source checkout and prebuilt artifact require access from the Agent Core team.

## Build and run identity

| Item | Value |
| --- | --- |
| Harness | Agent Core, the proprietary Go-based harness behind Alibaba’s AI product for Taobao merchants |
| Source revision | `897e95d5c8bf30ede82e7dc7ef7d31a03faef819` |
| Build | Go 1.25.9, Linux amd64, `CGO_ENABLED=0` |
| SHA-256, original executable | `368f4dba8b4e3eea7b3bd266277d4e60af5e28319ab969b618c5dca908d7f548` |
| SHA-256, original gzip | `99b5aa1ab4c5114c7ee6f8071b780c44eaf9b55050b312189f8f4fba2b6bcc0e` |
| Orchestrator | Harbor 0.25.0 with native Runta, Runta CLI 0.2.17, Runta SDK 0.2.6 |
| Dataset | `frontier-harness-eval/frontier-harness-eval@v1.1.0`, resolved to `sha256:9236400fc1a6619eb72a663445c580417be9bbbab32f816c7dff76d0a96ab24a` |
| Matrix | 45 Terminal-Bench 2.1 tasks and 17 Terminal Bench 4 tasks, five models, one scored attempt per task and model |
| Resources and limits | Fresh Runta VM and task container per attempt, task-defined 1–4 vCPU, 2–8 GiB RAM and 15–480 minutes of Agent time, with 32 GiB disk. The 17 tasks that declare a separate verifier retain that topology. |
| Runtime configuration | `AGENT_MODE=stdio`, `AGENT_HUB_SERVICE_PROFILE=independent_eval`, fresh state and an empty initial skill directory, tool lazy loading, six-zone context compaction, unattended interaction and retry of eligible interrupted model streams |
| Model and search | Fireworks at `https://api.fireworks.ai/inference/v1`, `reasoning_effort=max`, harness context window 500,000 and main-loop output budget 64,000 tokens. Tavily search uses a separate credential. GLM-5.3 was configured as text-only. |
| Scoring | Original Harbor verifier reward plus a separate lookup-review column. Four confirmed reference-lookup passes are scored as failures in the reviewed result. |

The Python adapter sends `initialize`, `config.update`, `session.new`, and `session.prompt` over stdio. It passes the original task instruction and the task container's working directory to the session. Runta binds the model and search credentials to their own egress rules. The initial sweep was resumed in shards after infrastructure interruptions, with up to eight concurrent trials in its final stage. The exported result contains one scored record for each of the 310 task/model combinations.

## Install and launch

On the orchestration machine, use Harbor 0.25.0 with Runta support, the Runta CLI, Go 1.25.9, `jq`, and Bash. Run `runta login` and save the Fireworks and Tavily keys as workspace secrets named `FIREWORKS_API_KEY` and `FRONTIER_SEARCH_API_KEY`.

From the root of the pinned Agent Core source checkout, build the candidate or set `FRONTIER_EVAL_BINARY` to the supplied, checksum-verified Linux artifact. The original binary hashes above identify the actual evaluated artifact.

```bash
test "$(git rev-parse HEAD)" = 897e95d5c8bf30ede82e7dc7ef7d31a03faef819 || exit 1
mkdir -p bin
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -buildvcs=false \
  -ldflags='-s -w' -o bin/agent-linux-amd64 ./cmd/agent
gzip -n -f bin/agent-linux-amd64
export FRONTIER_EVAL_BINARY="$PWD/bin/agent-linux-amd64.gz"
```

Run the following with the matching adapter checkout. The function takes a Fireworks model slug, a new job name, and optional Harbor arguments. The dry run validates the matrix without launching tasks. The loop launches five complete model jobs sequentially with eight concurrent tasks per job. This reproduces the evaluation configuration without depending on the original shard scheduler.

```bash
adapter="$PWD/scripts/frontier-eval"
dataset=frontier-harness-eval/frontier-harness-eval@sha256:9236400fc1a6619eb72a663445c580417be9bbbab32f816c7dff76d0a96ab24a
export FRONTIER_EVAL_COMMIT=897e95d5c8bf30ede82e7dc7ef7d31a03faef819
export PYTHONPATH="$adapter"
export PYTHONDONTWRITEBYTECODE=1
export RUNTA_CONFIG="${RUNTA_CONFIG:-$HOME/.config/runta/config.toml}"
export FIREWORKS_API_KEY=runta-secret-stub
export FRONTIER_SEARCH_API_KEY=runta-secret-stub

run_model() {
  local model="$1" job="$2" vision=true model_id
  shift 2
  if [[ "$model" == glm-5p3 ]]; then vision=false; fi
  model_id="accounts/fireworks/models/$model"
  FRONTIER_EVAL_RUNTIME_CONFIG="$(jq -ce --arg model "$model_id" --argjson vision "$vision" '
    .runnerModel = ("fireworks_ai/" + $model) |
    .provider.model = $model |
    .provider.supportsVision = $vision |
    .provider.reasoningEffort = "max"
  ' "$adapter/runtime-fireworks-deepseek-v11.example.json")" || return
  export FRONTIER_EVAL_RUNTIME_CONFIG
  harbor run -d "$dataset" -a harbor_runta_agent:AgentCore -e runta \
    --n-attempts 1 --n-concurrent 8 --override-storage-mb 32768 \
    --agent-setup-timeout-multiplier 2 \
    --allow-agent-host api.fireworks.ai --allow-agent-host api.tavily.com \
    --jobs-dir "$PWD/frontier-jobs" --job-name "$job" "$@"
}

run_model deepseek-v4p1-flash-1017 agent-core-config-check --dry-run || exit 1
for model in glm-5p3 glm-5p3-flash deepseek-v4p1-flash-1017 muse-spark-open kimi-k3; do
  run_model "$model" "agent-core-v11-$model" || exit 1
done
```

The dry run has been checked for each of the five model configurations. Harbor planned 62 trials per model. The dry run exercises configuration and dataset resolution.

Preserve the Harbor job directories for review. For an evidence-producing rerun, use the original archive hook or otherwise retain the Runta instances until final logs from the Agent and any separate verifier have been copied and checked. The initial sweep used `--no-delete` with a separate archive and instance cleanup process. The archived trial evidence includes Harbor `result.json`, verifier reward and outputs, Core JSON-RPC events, stderr, lifecycle and diagnostics, and per-call usage where available. The four review decisions have separate trajectory evidence. One scored result was recovered from a verifier that had finished before the trial cancellation was recorded.

## Recompute the candidate results

Use [trial-results.csv](trial-results.csv) to recompute the aggregates. Sum `raw_reward` and `reviewed_reward` separately over the 310 scored rows. The review uses only the four flagged passes. The strict-timeout sensitivity score also sets `reviewed_reward` to zero whenever `agent_timeout=true`.

For the Live-style cost metric, average `complete_model_cost_usd` over the available models for each task, then average the 61 tasks with at least one complete estimate and divide by the reviewed pass rate. The time metric uses `agent_verifier_seconds` across all 62 tasks. The observed spend is the sum of `observed_model_cost_usd`, including partial usage. The cache rate is observed cached input tokens divided by observed total input tokens.

| Measurement | Observed value |
| --- | ---: |
| Raw verifier | 195/310 (62.9%) |
| Reviewed | 191/310 (61.6%) |
| Reviewed with all marked timeouts scored as failures | 180/310 (58.1%) |
| Reviewed by subset | Terminal-Bench 2.1 180/225 (80.0%), Terminal Bench 4 11/85 (12.9%) |
| Estimated model cost per pass, reviewed | $1.057 |
| Agent-plus-verifier time per pass, reviewed | 27.9 minutes |
| Observed model cost across scored trials | $224.27 |
| Complete-cost coverage | 272/310 trials |
| Observed input-token cache rate | 95.3% |

The cost estimates use Fireworks list prices. There are 44 missing usage receipts across 38 scored trials. Complete cost is blank for those trials and all 310 rows still count toward pass rate. The one-sweep pass rate has a task-cluster bootstrap interval of 51.6%–71.3% at 95% confidence. The interval resamples tasks with their five model results and leaves run-to-run variation unmeasured. The public v1.1 Live comparison uses four attempts and Baseten. No matched-provider control was run.

[Harbor dataset](https://hub.harborframework.com/datasets/frontier-harness-eval/frontier-harness-eval) · [FrontierHarness Live](https://frontierharness.org/live/) · [Submission instructions](https://frontierharness.org/participate/)
