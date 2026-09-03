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
MODEL=""
RUN_ID=""
TASKS=""
OUT="runs"
CMD_TEMPLATE=""
TIMEOUT=5400
SECRET_NAME=""
SECRET_HOST=""

usage() {
  cat <<EOF
Usage: run-trials.sh --checkpoint NAME --harness NAME --run-id ID --tasks FILE
                     [--provider NAME] [--model ID] [--out DIR] [--cmd TEMPLATE]
                     [--timeout SEC]

  --tasks FILE    One task id per line: terminal-bench/<id> or datacurve/<id>
  --provider NAME Kimi K3 provider, must match the golden checkpoint's provider.
                  Default fireworks. One of: $PROVIDER_LIST
  --model ID      Override the model route. Must still be Kimi K3; the benchmark does
                  not vary the model. Required with --provider custom.
  --out DIR       Root output directory (default runs)
  --cmd TEMPLATE  Override the runner command. Placeholders: {task} {suite} {harness}
                  {model} {jobs}. Default templates are per suite, see reference.md.
  --timeout SEC   Per-task timeout in seconds (default 5400, matching task.toml)
  --secret-name NAME  Provider key to inject on egress. Defaults to the provider preset.
  --secret-host HOST  Host the key is injected for. Defaults to the provider preset.
                  Credential injection rules are per-runtime and are not carried by a
                  checkpoint, so each restored trial runtime needs the rule reapplied.

Re-running an existing --run-id only re-runs the listed tasks and leaves the rest.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --checkpoint) CHECKPOINT=$2; shift 2 ;;
    --harness) HARNESS=$2; shift 2 ;;
    --provider) PROVIDER=$2; shift 2 ;;
    --model) MODEL=$2; shift 2 ;;
    --run-id) RUN_ID=$2; shift 2 ;;
    --tasks) TASKS=$2; shift 2 ;;
    --out) OUT=$2; shift 2 ;;
    --cmd) CMD_TEMPLATE=$2; shift 2 ;;
    --timeout) TIMEOUT=$2; shift 2 ;;
    --secret-name) SECRET_NAME=$2; shift 2 ;;
    --secret-host) SECRET_HOST=$2; shift 2 ;;
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
SECRET_NAME=${SECRET_NAME:-$PROVIDER_SECRET}
SECRET_HOST=${SECRET_HOST:-$PROVIDER_HOST}
if [ -z "$MODEL" ]; then
  echo "--provider custom needs --model" >&2
  exit 2
fi
warn_unless_kimi_k3 "$MODEL"

: "${RUNTA_TOKEN:?RUNTA_TOKEN is not set}"
command -v runta >/dev/null || { echo "runta CLI not found" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq not found" >&2; exit 1; }
[ -r "$TASKS" ] || { echo "cannot read task list: $TASKS" >&2; exit 1; }

RUN_DIR="$OUT/$RUN_ID"
mkdir -p "$RUN_DIR/trials"

jq -n --arg run_id "$RUN_ID" --arg checkpoint "$CHECKPOINT" --arg harness "$HARNESS" \
      --arg model "$MODEL" --arg provider "$PROVIDER" \
      --arg started "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{run_id:$run_id, checkpoint:$checkpoint, harness:$harness, model:$model,
    provider:$provider, started_at:$started}' \
  > "$RUN_DIR/run.json"

# Harbor drives Terminal-Bench tasks; Pier drives DeepSWE tasks in air-gapped mode.
default_cmd() {
  case "$1" in
    terminal-bench)
      echo "harbor run -d terminal-bench/terminal-bench@4.0.0 --task-id {task} -a {harness} -m {model} --jobs-dir {jobs}" ;;
    datacurve)
      echo "pier run -p /work/deep-swe/tasks/{task} --agent {harness} --model {model} --output-dir {jobs}" ;;
    *)
      echo "" ;;
  esac
}

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
  slug=$(echo "$entry" | tr '/' '-')
  trial_dir="$RUN_DIR/trials/$slug"
  runtime="fh-$(printf '%s' "$RUN_ID-$slug" | tr -c 'a-zA-Z0-9-' '-' | cut -c1-48)"

  template=${CMD_TEMPLATE:-$(default_cmd "$suite")}
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

  # `checkpoint restore` returns as soon as the restore is accepted, while the runtime is
  # still provisioning. Until it finishes, exec fails with a 504 and secret rules with
  # FAILED_PRECONDITION, so wait for a usable runtime rather than scoring the race.
  ready=0
  for _ in $(seq 1 60); do
    if runta exec "$runtime" -- sh -lc 'exit 0' >>"$trial_dir/restore.log" 2>&1; then
      ready=1
      break
    fi
    sleep 5
  done
  if [ "$ready" -ne 1 ]; then
    echo "restored runtime never became ready for $entry" >&2
    jq -n --arg id "$entry" --arg t "$task" --arg rt "$runtime" \
      '{id:$id, title:$t, status:"infra_invalid", success:false,
        error:"restored runtime never became ready", runtime:$rt}' \
      > "$trial_dir/trial.json"
    runta rm "$runtime" >/dev/null 2>&1 || true
    continue
  fi

  # Injection rules live on the runtime, not in the checkpoint, so without this the
  # harness sends the stub placeholder to the provider and every turn fails on auth.
  if [ -n "$SECRET_NAME" ] && [ -n "$SECRET_HOST" ]; then
    runta secret rule set "$runtime" --secret "$SECRET_NAME" --host "$SECRET_HOST" \
      --header Authorization --template 'Bearer ${secret}' \
      >>"$trial_dir/restore.log" 2>&1 \
      || echo "warning: could not set the credential rule on $runtime" >&2
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
  runta cp "$runtime:/work/manifest.json" "$trial_dir/manifest.json" >/dev/null 2>&1 || true
  runta rm "$runtime" >/dev/null 2>&1 || echo "failed to delete runtime $runtime" >&2

  reward=$(extract "$trial_dir/jobs" '[.. | objects | (.resolved?, .is_resolved?, .reward?, .passed?)] | map(select(. != null)) | .[0]')
  cost=$(extract "$trial_dir/jobs" '[.. | objects | (.total_cost_usd?, .total_cost?, .cost_usd?)] | map(select(type == "number")) | .[0]')
  turns=$(extract "$trial_dir/jobs" '[.. | objects | (.n_steps?, .num_turns?, .steps?)] | map(select(type == "number")) | .[0]')
  cache=$(extract "$trial_dir/jobs" '[.. | objects | (.cache_hit_rate?, .cache_read_ratio?)] | map(select(type == "number")) | .[0]')

  case "$reward" in
    true|1|1.0) success=true ;;
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
    --argjson cost "${cost:-null}" --argjson turns "${turns:-null}" --argjson cache "${cache:-null}" \
    '{id:$id, title:$task, suite:$suite, status:$status, success:$success,
      duration_seconds:$duration, cost_first_cold_usd:$cost, turns:$turns,
      cache_hit_rate_normalized:$cache, exit_code:$exit_code,
      runtime:$runtime, checkpoint:$checkpoint,
      included_in_efficiency:$success}' \
    > "$trial_dir/trial.json"

  printf '=== [%s] %s in %ss (exit %s)\n' "$entry" "$status" "$duration" "$exit_code" >&2
done < "$TASKS"

echo >&2
echo "$passed/$total passed. Evidence in $RUN_DIR/trials/" >&2
echo "Next: node $(dirname "$0")/normalize-results.mjs --run $RUN_DIR --label \"$HARNESS\"" >&2
