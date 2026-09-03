#!/usr/bin/env bash
# Run benchmark tasks against a harness, one fresh golden-checkpoint restore per task,
# collecting trajectories and verifier logs as evidence.
set -euo pipefail

# shellcheck source=providers.sh
. "$(cd "$(dirname "$0")" && pwd)/providers.sh"

# The benchmark is fixed to Kimi K3; the provider is free. See providers.sh.
PROVIDER="fireworks"

CHECKPOINT=""
HARNESS=""
HARNESS_VERSION=""
MODEL=""
CHECKPOINT_MODEL=""
RUN_ID=""
TASKS=""
OUT="runs"
CMD_TEMPLATE=""
TERMINAL_CMD_TEMPLATE=""
DATACURVE_CMD_TEMPLATE=""
TIMEOUT=5400
MCODE_TERMINAL_BENCH_DATASET="terminal-bench/terminal-bench-2-1@sha256:7d7bdc1cbedad549fc1140404bd4dc45e5fd0ea7c4186773687d177ad3a0699a"
MCODE_DEEP_SWE_COMMIT="435ee89ec2f2e2289f33b0da4f992f0b7b7266b9"

usage() {
  cat <<EOF
Usage: run-trials.sh --checkpoint NAME --harness NAME --run-id ID --tasks FILE
                     [--harness-version VER] [--provider NAME] [--model ID]
                     [--checkpoint-model ID]
                     [--out DIR] [--cmd TEMPLATE]
                     [--terminal-cmd TEMPLATE] [--datacurve-cmd TEMPLATE]
                     [--timeout SEC]

  --tasks FILE    One task id per line: terminal-bench/<id> or datacurve/<id>
  --harness-version VER
                  Exact packaged agent version executed by the runner, if applicable.
  --provider NAME Kimi K3 provider, must match the golden checkpoint's provider.
                  Default fireworks. One of: $PROVIDER_LIST
  --model ID      Override the model route. Must still be Kimi K3; the benchmark does
                  not vary the model. Required with --provider custom.
  --checkpoint-model ID
                  Model route recorded by the checkpoint when it differs from the
                  agent-facing route. Defaults to --model.
  --out DIR       Root output directory (default runs)
  --cmd TEMPLATE  Override the runner command. Placeholders: {task} {suite} {harness}
                  {model} {jobs}. Default templates are per suite, see reference.md.
  --terminal-cmd TEMPLATE
                  Override only the terminal-bench/* runner command.
  --datacurve-cmd TEMPLATE
                  Override only the datacurve/* runner command.
  --timeout SEC   Per-task timeout in seconds (default 5400, matching task.toml)

Re-running an existing --run-id with the same immutable configuration only re-runs the
listed tasks and leaves the rest. Configuration changes require a new run ID.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --checkpoint) CHECKPOINT=$2; shift 2 ;;
    --harness) HARNESS=$2; shift 2 ;;
    --harness-version) HARNESS_VERSION=$2; shift 2 ;;
    --provider) PROVIDER=$2; shift 2 ;;
    --model) MODEL=$2; shift 2 ;;
    --checkpoint-model) CHECKPOINT_MODEL=$2; shift 2 ;;
    --run-id) RUN_ID=$2; shift 2 ;;
    --tasks) TASKS=$2; shift 2 ;;
    --out) OUT=$2; shift 2 ;;
    --cmd) CMD_TEMPLATE=$2; shift 2 ;;
    --terminal-cmd) TERMINAL_CMD_TEMPLATE=$2; shift 2 ;;
    --datacurve-cmd) DATACURVE_CMD_TEMPLATE=$2; shift 2 ;;
    --timeout) TIMEOUT=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

for required in CHECKPOINT HARNESS RUN_ID TASKS; do
  if [ -z "${!required}" ]; then
    echo "missing --$(echo "$required" | tr 'A-Z_' 'a-z-')" >&2
    usage >&2
    exit 2
  fi
done

if ! resolve_provider "$PROVIDER"; then
  echo "unknown --provider $PROVIDER; expected one of: $PROVIDER_LIST" >&2
  exit 2
fi
MODEL=${MODEL:-$PROVIDER_MODEL}
if [ -z "$MODEL" ]; then
  echo "--provider custom needs --model" >&2
  exit 2
fi
CHECKPOINT_MODEL=${CHECKPOINT_MODEL:-$MODEL}
warn_unless_kimi_k3 "$MODEL"
case "$TIMEOUT" in
  ""|*[!0-9]*) echo "invalid --timeout: $TIMEOUT" >&2; exit 2 ;;
esac
case "$CHECKPOINT" in
  *[!A-Za-z0-9._-]*) echo "invalid --checkpoint: $CHECKPOINT" >&2; exit 2 ;;
esac
case "$RUN_ID" in
  *[!A-Za-z0-9._-]*) echo "invalid --run-id: $RUN_ID" >&2; exit 2 ;;
esac
case "$HARNESS" in
  *[!A-Za-z0-9._:/@+-]*) echo "invalid --harness: $HARNESS" >&2; exit 2 ;;
esac
case "$HARNESS_VERSION" in
  *[!A-Za-z0-9._+-]*) echo "invalid --harness-version: $HARNESS_VERSION" >&2; exit 2 ;;
esac
case "$MODEL" in
  *[!A-Za-z0-9._:/@+-]*) echo "invalid --model: $MODEL" >&2; exit 2 ;;
esac
case "$CHECKPOINT_MODEL" in
  *[!A-Za-z0-9._:/@+-]*) echo "invalid --checkpoint-model: $CHECKPOINT_MODEL" >&2; exit 2 ;;
esac

: "${RUNTA_TOKEN:?RUNTA_TOKEN is not set}"
command -v runta >/dev/null || { echo "runta CLI not found" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq not found" >&2; exit 1; }
[ -r "$TASKS" ] || { echo "cannot read task list: $TASKS" >&2; exit 1; }

# Harbor drives Terminal-Bench tasks; Pier drives DeepSWE tasks in air-gapped mode.
default_cmd() {
  case "$1" in
    terminal-bench)
      echo "harbor run -d terminal-bench/terminal-bench-2-1@sha256:7d7bdc1cbedad549fc1140404bd4dc45e5fd0ea7c4186773687d177ad3a0699a --include-task-name {suite}/{task} -a {harness} -m {model} --jobs-dir {jobs}" ;;
    datacurve)
      echo "pier run -p /work/deep-swe/tasks/{task} --agent {harness} --model {model} --output-dir {jobs}" ;;
    *)
      echo "" ;;
  esac
}

sha256_text() {
  if command -v sha256sum >/dev/null; then
    printf '%s' "$1" | sha256sum | cut -d' ' -f1
  elif command -v shasum >/dev/null; then
    printf '%s' "$1" | shasum -a 256 | cut -d' ' -f1
  else
    echo "sha256sum or shasum is required to identify runner commands" >&2
    return 1
  fi
}

EFFECTIVE_TERMINAL_CMD=${CMD_TEMPLATE:-${TERMINAL_CMD_TEMPLATE:-$(default_cmd terminal-bench)}}
EFFECTIVE_DATACURVE_CMD=${CMD_TEMPLATE:-${DATACURVE_CMD_TEMPLATE:-$(default_cmd datacurve)}}
TERMINAL_CMD_SHA256=$(sha256_text "$EFFECTIVE_TERMINAL_CMD")
DATACURVE_CMD_SHA256=$(sha256_text "$EFFECTIVE_DATACURVE_CMD")

RUN_DIR="$OUT/$RUN_ID"
mkdir -p "$RUN_DIR/trials"

if [ -f "$RUN_DIR/run.json" ]; then
  if ! jq -e --arg checkpoint "$CHECKPOINT" --arg harness "$HARNESS" \
      --arg harness_version "$HARNESS_VERSION" --arg model "$MODEL" \
      --arg checkpoint_model "$CHECKPOINT_MODEL" --arg provider "$PROVIDER" \
      --arg terminal_cmd_sha256 "$TERMINAL_CMD_SHA256" \
      --arg datacurve_cmd_sha256 "$DATACURVE_CMD_SHA256" --argjson timeout "$TIMEOUT" \
      '.checkpoint == $checkpoint and .harness == $harness and
       (.harness_version // "") == $harness_version and .model == $model and
       .checkpoint_model == $checkpoint_model and .provider == $provider and
       .timeout_seconds == $timeout and .terminal_command_sha256 == $terminal_cmd_sha256 and
       .datacurve_command_sha256 == $datacurve_cmd_sha256' "$RUN_DIR/run.json" >/dev/null; then
    echo "run id '$RUN_ID' already exists with a different immutable run configuration" >&2
    exit 2
  fi
else
  jq -n --arg run_id "$RUN_ID" --arg checkpoint "$CHECKPOINT" --arg harness "$HARNESS" \
        --arg harness_version "$HARNESS_VERSION" \
        --arg model "$MODEL" --arg checkpoint_model "$CHECKPOINT_MODEL" \
        --arg provider "$PROVIDER" --arg terminal_cmd_sha256 "$TERMINAL_CMD_SHA256" \
        --arg datacurve_cmd_sha256 "$DATACURVE_CMD_SHA256" --argjson timeout "$TIMEOUT" \
        --arg started "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{run_id:$run_id, checkpoint:$checkpoint, harness:$harness,
      harness_version:(if $harness_version == "" then null else $harness_version end),
      model:$model, checkpoint_model:$checkpoint_model, provider:$provider,
      timeout_seconds:$timeout, terminal_command_sha256:$terminal_cmd_sha256,
      datacurve_command_sha256:$datacurve_cmd_sha256, started_at:$started}' \
    > "$RUN_DIR/run.json"
fi

render() {
  echo "$1" \
    | sed "s|{task}|$2|g; s|{suite}|$3|g; s|{harness}|$HARNESS|g; s|{model}|$MODEL|g; s|{jobs}|$4|g"
}

# Reward field names differ between Harbor and Pier releases, so probe the common ones
# across every JSON file the runner produced and take the first usable value.
extract() {
  local dir=$1 filter=$2 file value
  [ -d "$dir" ] || return 0
  while IFS= read -r file; do
    value=$(jq -c "$filter" "$file" 2>/dev/null) || continue
    if [ -n "$value" ] && [ "$value" != "null" ]; then
      printf '%s' "$value"
      return 0
    fi
  done < <(find "$dir" -name '*.json' -size -8M 2>/dev/null)
}

total=0
passed=0

while IFS= read -r entry || [ -n "$entry" ]; do
  entry=$(echo "$entry" | tr -d '\r' | sed 's/#.*//; s/^ *//; s/ *$//')
  [ -n "$entry" ] || continue

  suite=${entry%%/*}
  task=${entry#*/}
  case "$suite" in
    terminal-bench|datacurve) ;;
    *) echo "unsupported task suite in '$entry'" >&2; exit 2 ;;
  esac
  case "$task" in
    ""|*[!A-Za-z0-9._+-]*) echo "invalid task id in '$entry'" >&2; exit 2 ;;
  esac
  slug=$(echo "$entry" | tr '/' '-')
  trial_dir="$RUN_DIR/trials/$slug"
  runtime="fh-$(printf '%s' "$RUN_ID-$slug" | tr -c 'a-zA-Z0-9-' '-' | cut -c1-48)"

  case "$suite" in
    terminal-bench) template=$EFFECTIVE_TERMINAL_CMD ;;
    datacurve) template=$EFFECTIVE_DATACURVE_CMD ;;
    *) template="" ;;
  esac
  if [ -z "$template" ]; then
    echo "no runner template for suite '$suite'; pass --cmd" >&2
    exit 1
  fi

  total=$((total + 1))
  rm -rf "$trial_dir"
  mkdir -p "$trial_dir"
  printf '\n=== [%s] restoring %s\n' "$entry" "$CHECKPOINT" >&2

  status=success
  if ! runta checkpoint restore "$CHECKPOINT" "$runtime" >"$trial_dir/restore.log" 2>&1; then
    echo "restore failed for $entry" >&2
    jq -n --arg id "$entry" --arg t "$task" \
      '{id:$id, title:$t, status:"infra_invalid", success:false, error:"checkpoint restore failed"}' \
      > "$trial_dir/trial.json"
    continue
  fi

  set +e
  runta cp "$runtime:/work/manifest.json" "$trial_dir/manifest.json" \
    >"$trial_dir/manifest-check.log" 2>&1
  manifest_exit=$?
  identity_exit=0
  if [ "$manifest_exit" -eq 0 ] && [ "$HARNESS" = mcode ]; then
    runta exec "$runtime" -- sh -lc 'set -eu
      tasks_sha256=$(find /work/frontierharness-tasks -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d" " -f1)
      terminal_bench_tasks_sha256=$(find /work/terminal-bench/tasks -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d" " -f1)
      deep_swe_tasks_sha256=$(find /work/deep-swe/tasks -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d" " -f1)
      deep_swe_commit=$(git -C /work/deep-swe rev-parse HEAD)
      mcode_bundle_sha256=$(sha256sum /work/mcode-runtime.tar.gz | cut -d" " -f1)
      mcode_agent_sha256=$(sha256sum /work/frontierharness_mcode.py | cut -d" " -f1)
      jq -n --arg tasks_sha256 "$tasks_sha256" \
        --arg terminal_bench_tasks_sha256 "$terminal_bench_tasks_sha256" \
        --arg deep_swe_tasks_sha256 "$deep_swe_tasks_sha256" \
        --arg deep_swe_commit "$deep_swe_commit" \
        --arg mcode_bundle_sha256 "$mcode_bundle_sha256" \
        --arg mcode_agent_sha256 "$mcode_agent_sha256" \
        "{tasks_sha256:\$tasks_sha256,
          terminal_bench_tasks_sha256:\$terminal_bench_tasks_sha256,
          deep_swe_tasks_sha256:\$deep_swe_tasks_sha256,
          deep_swe_commit:\$deep_swe_commit,
          mcode_bundle_sha256:\$mcode_bundle_sha256,
          mcode_agent_sha256:\$mcode_agent_sha256}" \
        > /work/evidence/checkpoint-identity.json' \
      >>"$trial_dir/manifest-check.log" 2>&1
    identity_exit=$?
    if [ "$identity_exit" -eq 0 ]; then
      runta cp "$runtime:/work/evidence/checkpoint-identity.json" \
        "$trial_dir/checkpoint-identity.json" >>"$trial_dir/manifest-check.log" 2>&1
      identity_exit=$?
    fi
  else
    printf '{}\n' > "$trial_dir/checkpoint-identity.json"
  fi
  set -e
  checkpoint_manifest=""
  if [ "$manifest_exit" -eq 0 ]; then
    checkpoint_manifest=$(cat "$trial_dir/manifest.json")
  fi
  manifest_valid=false
  if [ "$manifest_exit" -eq 0 ] && [ "$identity_exit" -eq 0 ] && jq -e \
      --slurpfile actual "$trial_dir/checkpoint-identity.json" \
      --arg harness "$HARNESS" --arg harness_version "$HARNESS_VERSION" \
      --arg model "$CHECKPOINT_MODEL" --arg provider "$PROVIDER" \
      --arg terminal_dataset "$MCODE_TERMINAL_BENCH_DATASET" \
      --arg deep_swe_commit "$MCODE_DEEP_SWE_COMMIT" \
      '(.harness // "") == $harness and (.provider // "") == $provider and
       (.model // "") == $model and
       ($harness_version == "" or (.harness_version // "") == $harness_version) and
       ($harness != "mcode" or
         (.task_count == 30 and .terminal_bench_overlay_count == 21 and
          .deep_swe_overlay_count == 9 and .terminal_bench_dataset == $terminal_dataset and
          .deep_swe_commit == $deep_swe_commit and
          ((.tasks_sha256 // "") | test("^[0-9a-f]{64}$")) and
          ((.terminal_bench_tasks_sha256 // "") | test("^[0-9a-f]{64}$")) and
          ((.deep_swe_tasks_sha256 // "") | test("^[0-9a-f]{64}$")) and
          ((.mcode_bundle_sha256 // "") | test("^[0-9a-f]{64}$")) and
          ((.mcode_agent_sha256 // "") | test("^[0-9a-f]{64}$")) and
          .tasks_sha256 == $actual[0].tasks_sha256 and
          .terminal_bench_tasks_sha256 == $actual[0].terminal_bench_tasks_sha256 and
          .deep_swe_tasks_sha256 == $actual[0].deep_swe_tasks_sha256 and
          .deep_swe_commit == $actual[0].deep_swe_commit and
          .mcode_bundle_sha256 == $actual[0].mcode_bundle_sha256 and
          .mcode_agent_sha256 == $actual[0].mcode_agent_sha256))' \
      "$trial_dir/manifest.json" \
      >/dev/null 2>&1; then
    manifest_valid=true
  fi
  if [ "$manifest_valid" != true ]; then
    echo "checkpoint manifest mismatch or incomplete task assets for $entry" >&2
    jq -n --arg id "$entry" --arg t "$task" \
      --arg observed_manifest "$checkpoint_manifest" \
      '{id:$id, title:$t, status:"infra_invalid", success:false,
        error:"checkpoint manifest mismatch or incomplete task assets",
        observed_manifest:$observed_manifest}' \
      > "$trial_dir/trial.json"
    runta rm "$runtime" >/dev/null 2>&1 || true
    continue
  fi

  jobs_dir="/work/jobs/$slug"
  command=$(render "$template" "$task" "$suite" "$jobs_dir")
  started=$(date +%s)

  # Never abort the loop on a task failure: a failing task is a data point.
  set +e
  runta exec "$runtime" -- sh -lc \
    "export PATH=\"\$HOME/.local/bin:\$PATH\"; mkdir -p $jobs_dir; cd /work; timeout $TIMEOUT $command" \
    >"$trial_dir/runner.log" 2>&1
  exit_code=$?
  set -e
  duration=$(( $(date +%s) - started ))

  runta cp "$runtime:$jobs_dir" "$trial_dir/jobs" >/dev/null 2>&1 \
    || echo "no job artifacts collected for $entry" >&2
  runta rm "$runtime" >/dev/null 2>&1 || echo "failed to delete runtime $runtime" >&2

  reward=$(extract "$trial_dir/jobs" '[.. | objects |
    (.verifier_result?.rewards?.reward?, .rewards?.reward?, .resolved?,
     .is_resolved?, .passed?)] |
    map(select(type == "number" or type == "boolean")) | .[0]')
  exception=$(extract "$trial_dir/jobs" '[.. | objects | .exception_info?] |
    map(select(. != null)) | .[0]')
  cost=$(extract "$trial_dir/jobs" '[.. | objects | (.total_cost_usd?, .total_cost?, .cost_usd?)] | map(select(type == "number")) | .[0]')
  turns=$(extract "$trial_dir/jobs" '[.. | objects | (.n_steps?, .num_turns?, .steps?)] | map(select(type == "number")) | .[0]')
  cache=$(extract "$trial_dir/jobs" '[.. | objects | (.cache_hit_rate?, .cache_read_ratio?)] | map(select(type == "number")) | .[0]')

  case "$reward:$exception" in
    true:|1:|1.0:) success=true ;;
    *) success=false ;;
  esac
  if [ "$exit_code" -eq 124 ]; then
    status=timeout
    success=false
  elif [ "$success" = true ]; then
    status=success
    passed=$((passed + 1))
  else
    status=failure
  fi

  jq -n \
    --arg id "$entry" --arg task "$task" --arg suite "$suite" --arg status "$status" \
    --arg runtime "$runtime" --arg checkpoint "$CHECKPOINT" \
    --argjson success "$success" --argjson duration "$duration" --argjson exit_code "$exit_code" \
    --argjson exception_info "${exception:-null}" \
    --argjson cost "${cost:-null}" --argjson turns "${turns:-null}" --argjson cache "${cache:-null}" \
    '{id:$id, title:$task, suite:$suite, status:$status, success:$success,
      duration_seconds:$duration, cost_first_cold_usd:$cost, turns:$turns,
      cache_hit_rate_normalized:$cache, exit_code:$exit_code,
      exception_info:$exception_info,
      runtime:$runtime, checkpoint:$checkpoint,
      included_in_efficiency:$success}' \
    > "$trial_dir/trial.json"

  printf '=== [%s] %s in %ss (exit %s)\n' "$entry" "$status" "$duration" "$exit_code" >&2
done < "$TASKS"

echo >&2
echo "$passed/$total passed. Evidence in $RUN_DIR/trials/" >&2
echo "Next: node $(dirname "$0")/normalize-results.mjs --run $RUN_DIR --label \"$HARNESS\"" >&2
