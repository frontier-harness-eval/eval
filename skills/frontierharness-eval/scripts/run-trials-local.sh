#!/usr/bin/env bash
# Local Docker transport for FrontierHarness. Each suite runs on the host and
# writes its native evidence into the shared scoring and reporting contract.
set -euo pipefail

# shellcheck source=providers.sh
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
. "$SCRIPT_DIR/providers.sh"
# shellcheck source=transport.sh
. "$SCRIPT_DIR/transport.sh"
. "$SCRIPT_DIR/task-inputs.sh"
command -v python3 >/dev/null || { echo "python3 is required for cost accounting" >&2; exit 2; }

# DeepSWE corpus pin, matching provision-golden-checkpoint.sh.
DEEP_SWE_REF="435ee89ec2f2e2289f33b0da4f992f0b7b7266b9"

# Reuse the benchmark provider defaults and accept custom model routes.
PROVIDER=""

HARNESS=""
MODEL=""
RUN_ID=""
TASKS="tasks"
OUT="runs"
CMD_TEMPLATE=""
TIMEOUT=5400
DEEP_SWE=".fh-local/deep-swe"
PREPULL=1
TASK_PLATFORM=${FH_TASK_PLATFORM:-linux/amd64}
SECRET_NAME=""
SECRET_HOST=""

usage() {
  cat <<EOF
Usage: run-trials-local.sh --harness NAME --run-id ID
                     [--tasks PATH] [--provider NAME] [--model ID] [--out DIR]
                     [--cmd TEMPLATE] [--timeout SEC] [--deep-swe PATH]
                     [--secret-name ENV_VAR] [--no-prepull]

Run benchmark tasks locally with Docker + Harbor/Pier. No Runta dependency.

  --tasks PATH    Either a directory of <task>/task.toml definitions, or a file with
                  one task id per line: terminal-bench/<id> or datacurve/<id>.
                  Defaults to the repo's tasks/ directory, i.e. the full published set.
  --provider NAME Provider route. Default fireworks. One of: $PROVIDER_LIST
                  The provider preset's key env var (see providers.sh) must be
                  exported so Harbor/Pier adapters can reach the model.
  --model ID      Override the model route. Required with --provider custom.
  --out DIR       Root output directory (default runs)
  --cmd TEMPLATE  Override the runner command. Placeholders: {task} {suite} {harness}
                  {model} {jobs} {deep_swe}. Default templates are per suite.
  --timeout SEC   Per-task watchdog in seconds (default 5400, matching task.toml)
  --deep-swe PATH Local checkout of the DeepSWE corpus (default .fh-local/deep-swe).
                  Missing corpus objects are fetched into the local Git cache.
  --secret-name NAME  Environment variable holding the provider key. Defaults to the
                  provider preset. The script only checks it is set and non-empty.
  --secret-host HOST  Inference host for custom Harbor routes.
  --no-prepull    Skip the per-task docker pull (Harbor/Pier pull on demand instead).

Prerequisites: Docker with Compose, Git, jq, Python 3.11+, GNU timeout (brew install
coreutils on macOS), harbor==0.22.0 for terminal-bench tasks
(uv tool install harbor==0.22.0), datacurve-pier==0.3.1 for datacurve tasks
(uv tool install datacurve-pier==0.3.1).

Re-running an existing --run-id keeps every valid trial (first valid attempt stays
canonical) and retries infra-invalid ones. Use a new --run-id for a new experiment.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --harness) HARNESS=$2; shift 2 ;;
    --provider) PROVIDER=$2; shift 2 ;;
    --model) MODEL=$2; shift 2 ;;
    --run-id) RUN_ID=$2; shift 2 ;;
    --tasks) TASKS=$2; shift 2 ;;
    --out) OUT=$2; shift 2 ;;
    --cmd) CMD_TEMPLATE=$2; shift 2 ;;
    --timeout) TIMEOUT=$2; shift 2 ;;
    --deep-swe) DEEP_SWE=$2; shift 2 ;;
    --secret-name) SECRET_NAME=$2; shift 2 ;;
    --secret-host) SECRET_HOST=$2; shift 2 ;;
    --no-prepull) PREPULL=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$TIMEOUT" in
  ''|*[!0-9]*|0) echo "--timeout must be a positive integer" >&2; exit 2 ;;
esac

for required in HARNESS RUN_ID; do
  if [ -z "${!required}" ]; then
    echo "missing --$(echo "$required" | tr 'A-Z_' 'a-z-')" >&2
    usage >&2
    exit 2
  fi
done

if [[ ! "$RUN_ID" =~ ^[A-Za-z0-9_-][A-Za-z0-9._-]*$ ]]; then
  echo "--run-id must be a single directory name starting with a letter, digit, underscore or dash" >&2
  exit 2
fi

PROVIDER=${PROVIDER:-fireworks}
if ! resolve_provider "$PROVIDER"; then
  echo "unknown --provider $PROVIDER; expected one of: $PROVIDER_LIST" >&2
  exit 2
fi
MODEL=${MODEL:-$PROVIDER_MODEL}
SECRET_NAME=${SECRET_NAME:-$PROVIDER_SECRET}
SECRET_HOST=${SECRET_HOST:-$PROVIDER_HOST}
if [ -n "$SECRET_NAME" ] && [[ ! "$SECRET_NAME" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
  echo "invalid --secret-name" >&2; exit 2
fi
if [ -z "$MODEL" ]; then
  echo "--provider custom needs --model" >&2
  exit 2
fi

RUN_DIR="$OUT/$RUN_ID"
TASK_SOURCE=repository-v1
[ -z "$CMD_TEMPLATE" ] || TASK_SOURCE=custom
# Prerequisites. The runner executes Harbor/Pier as local child processes, so the
# provider credential rides along in the environment they inherit.
command -v docker >/dev/null || { echo "docker not found; install Docker Desktop or a Docker engine" >&2; exit 2; }
docker info >/dev/null 2>&1 || { echo "docker daemon is not reachable; start Docker first" >&2; exit 2; }
command -v jq >/dev/null || { echo "jq not found" >&2; exit 2; }
if command -v timeout >/dev/null; then
  TIMEOUT_BIN=timeout
elif command -v gtimeout >/dev/null; then
  TIMEOUT_BIN=gtimeout
else
  echo "GNU timeout not found; on macOS install it with: brew install coreutils" >&2
  exit 2
fi
if [ "$PROVIDER" = fireworks ]; then
  # The pinned adapters use the LiteLLM name for Fireworks.
  export FIREWORKS_AI_API_KEY="${!SECRET_NAME:-${FIREWORKS_AI_API_KEY:-}}"
  if [ "$SECRET_NAME" = FIREWORKS_API_KEY ]; then export FIREWORKS_API_KEY="$FIREWORKS_AI_API_KEY"; fi
fi
if [ -n "$SECRET_NAME" ] && [ -z "${!SECRET_NAME:-}" ]; then
  echo "$SECRET_NAME is not set; export it so Harbor/Pier adapters can reach the model provider" >&2
  exit 2
fi

# The task list is either a directory of task definitions or a plain list file,
# identical to run-trials.sh.
TASK_LIST=$(mktemp)
cleanup() { rm -f "$TASK_LIST"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

list_task_ids "$TASKS" > "$TASK_LIST"
[ -s "$TASK_LIST" ] || { echo "no tasks found in $TASKS" >&2; exit 1; }

# Only the suites actually present in the list gate their runner.
need_harbor=$(grep -c '^terminal-bench/' "$TASK_LIST" || true)
need_pier=$(grep -c '^datacurve/' "$TASK_LIST" || true)
if [ "$need_harbor" -gt 0 ]; then
  command -v harbor >/dev/null || { echo "harbor not found; install with: uv tool install harbor==0.22.0" >&2; exit 2; }
fi
if [ "$need_pier" -gt 0 ]; then
  command -v pier >/dev/null || { echo "pier not found; install with: uv tool install datacurve-pier==0.3.1" >&2; exit 2; }
fi

# Pier reads DeepSWE task definitions and verifier material from the pinned corpus.
if [ "$need_pier" -gt 0 ] && [ "$TASK_SOURCE" != repository-v1 ] &&
   { [ "$PREPULL" -eq 1 ] || [[ "$CMD_TEMPLATE" == *'{deep_swe}'* ]]; }; then
  if [ ! -d "$DEEP_SWE/tasks" ]; then
    echo "cloning the DeepSWE corpus into $DEEP_SWE (pinned at $DEEP_SWE_REF)" >&2
    git clone --quiet https://github.com/datacurve-ai/deep-swe "$DEEP_SWE"
    git -C "$DEEP_SWE" checkout --quiet "$DEEP_SWE_REF"
  elif [ -d "$DEEP_SWE/.git" ]; then
    corpus_head=$(git -C "$DEEP_SWE" rev-parse HEAD 2>/dev/null || echo unknown)
    if [ "$corpus_head" != "$DEEP_SWE_REF" ]; then
      echo "DeepSWE corpus at $DEEP_SWE is $corpus_head; the benchmark pins $DEEP_SWE_REF. Fix the checkout or pass --deep-swe." >&2
      exit 2
    fi
  else
    echo "warning: $DEEP_SWE is not a git checkout; cannot verify the pinned corpus ref $DEEP_SWE_REF" >&2
  fi
  DEEP_SWE_ABS=$(cd "$DEEP_SWE" && pwd)
fi

mkdir -p "$RUN_DIR/trials"

# Record the host layer separately from Harbor/Pier task network controls.
EGRESS_POLICY=$(jq -cn '{mode:"unrestricted", scope:"host", allowed_hosts:null}')

catalog=$(task_catalog_digest)
if [ ! -f "$RUN_DIR/run.json" ]; then
  jq -n --arg run_id "$RUN_ID" --arg harness "$HARNESS" --arg model "$MODEL" --arg provider "$PROVIDER" \
    --arg cmd "$CMD_TEMPLATE" --argjson timeout "$TIMEOUT" --argjson egress_policy "$EGRESS_POLICY" \
    --arg platform "$TASK_PLATFORM" --arg task_source "$TASK_SOURCE" --arg catalog "$catalog" --arg secret_name "$SECRET_NAME" --arg secret_host "$SECRET_HOST" --arg started "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{run_id:$run_id, backend:"local-docker", task_platform:$platform, task_source:$task_source, task_catalog_sha256:$catalog, secret_name:$secret_name, secret_host:$secret_host, topology:"local-docker", harness:$harness,
    model:$model, provider:$provider, cmd_template:$cmd, timeout_seconds:$timeout,
    started_at:$started, egress_policy:$egress_policy, methodology_comparable:false,
    methodology_notes:["Local Docker topology (run-trials-local.sh): tasks share one Docker host and each trial creates fresh containers.",
      "The host has no Runta egress proxy. Harbor/Pier apply task-level network controls. Agent credentials come from the host environment.",
      "The published baselines ran on fresh Runta golden-checkpoint restores with a runtime-level allowlist. A matched control run under equivalent conditions is required before claiming comparability; this result is observational."]}' \
  | publish_manifest "$RUN_DIR/run.json"
fi
jq -e --argjson policy "$EGRESS_POLICY" '.egress_policy == $policy' "$RUN_DIR/run.json" >/dev/null \
  || { echo "run egress policy differs or is unrecorded; use a new --run-id (existing evidence retained)" >&2; exit 2; }
jq -e --arg harness "$HARNESS" --arg model "$MODEL" --arg provider "$PROVIDER" \
  --arg platform "$TASK_PLATFORM" --arg cmd "$CMD_TEMPLATE" --argjson timeout "$TIMEOUT" \
  '.topology == "local-docker" and .harness == $harness and .model == $model
   and (.backend // "local-docker") == "local-docker" and (.profile // "") == ""
   and .provider == $provider and (.cmd_template // "") == $cmd
   and (.task_platform // "linux/amd64") == $platform and (.timeout_seconds // 5400) == $timeout' "$RUN_DIR/run.json" >/dev/null \
  || { echo "run configuration differs; use a new --run-id" >&2; exit 2; }
jq -e --arg source "$TASK_SOURCE" --arg catalog "$catalog" --arg secret "$SECRET_NAME" --arg host "$SECRET_HOST" \
  '(.task_source // "legacy") == $source and (.task_catalog_sha256 // "") == $catalog
   and (.secret_name // $secret) == $secret and (.secret_host // $host) == $host' "$RUN_DIR/run.json" >/dev/null \
  || { echo "run inputs or provider configuration differ; use a new --run-id" >&2; exit 2; }

render() {
  local rendered=$1
  rendered=${rendered//\{task\}/$(shell_quote "$2")}
  rendered=${rendered//\{suite\}/$(shell_quote "$3")}
  rendered=${rendered//\{harness\}/$(shell_quote "$HARNESS")}
  rendered=${rendered//\{model\}/$(shell_quote "$MODEL")}
  rendered=${rendered//\{jobs\}/$(shell_quote "$4")}
  rendered=${rendered//\{deep_swe\}/$(shell_quote "${DEEP_SWE_ABS:-.fh-local/deep-swe}")}
  printf '%s\n' "$rendered"
}

record_infra() {
  local error=$1
  jq -n --arg id "$entry" --arg task "$task" --arg suite "$suite" --arg error "$error" \
    --arg command "$command" \
    '{id:$id, title:$task, suite:$suite, status:"infra_invalid", success:false,
      runtime:"local-docker", error:$error,
      runner_command:$command}' > "$trial_dir/trial.json.tmp"
  mv "$trial_dir/trial.json.tmp" "$trial_dir/trial.json"
  echo "$entry: $error" >&2
}

# Pull this task's image before the timed run, so image download time and pull
# failures stay out of the scored execution. DeepSWE's pinned corpus is
# authoritative for its image; Terminal-Bench resolves from the task metadata.
prepare_image() {
  local image toml
  if [ "$TASK_SOURCE" = repository-v1 ]; then
    toml="$input_path/task.toml"
  elif [ "$suite" = datacurve ]; then
    toml="$DEEP_SWE_ABS/tasks/$task/task.toml"
    [ -f "$toml" ] || return 1
  else
    toml="$TASKS/$task/task.toml"
    [ -f "$toml" ] || toml="tasks/$task/task.toml"
    [ -f "$toml" ] || toml="$SCRIPT_DIR/../../../tasks/$task/task.toml"
    [ -f "$toml" ] || return 0 # A custom --cmd may prepare its own environment.
  fi
  image=$(awk -F'"' '/^docker_image *=/ { print $2; exit }' "$toml")
  [ -n "$image" ] || return 0
  "$TIMEOUT_BIN" 1800 docker pull --platform "$TASK_PLATFORM" "$image"
}

total=0
passed=0
invalid=0

while IFS= read -r entry || [ -n "$entry" ]; do
  [ -n "$entry" ] || continue
  if [[ ! "$entry" =~ ^[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+$ ]]; then
    echo "invalid task id: $entry" >&2
    exit 2
  fi

  suite=${entry%%/*}
  task=${entry#*/}
  slug=$(echo "$entry" | tr '/' '-')
  lock_trial
  trial_dir="$RUN_DIR/trials/$slug"
  if [ "$TASK_SOURCE" = repository-v1 ]; then
    input_path="$(cd "$RUN_DIR" && pwd)/trials/$slug/inputs/$task"
    command=$(repository_command "$suite" "$input_path" "$HARNESS" "$MODEL" "$trial_dir/jobs")
  else
    command=$(render "$CMD_TEMPLATE" "$task" "$suite" "$trial_dir/jobs")
  fi
  total=$((total + 1))

  # Re-score any retained evidence first: an interrupted run can leave a finished
  # job behind, and re-running it would waste model spend. Scoring is idempotent
  # and follows the same collector rules as run-trials.sh.
  if [ -d "$trial_dir/jobs" ]; then
    if [ ! -f "$trial_dir/trial.json" ]; then
      jq -n --arg id "$entry" --arg task "$task" --arg suite "$suite" \
        '{id:$id, title:$task, suite:$suite, status:"infra_invalid", success:false}' \
        > "$trial_dir/trial.json"
    fi
    python3 "$SCRIPT_DIR/calculate-cost.py" --trial "$trial_dir" --model "$MODEL" --harness "$HARNESS" --score --write
  fi
  # Preserve the first valid attempt, whether it passed or failed.
  if [ -f "$trial_dir/trial.json" ] && jq -e \
    '.status == "success" or .status == "failure"' "$trial_dir/trial.json" >/dev/null; then
    echo "[$entry] keeping first valid attempt" >&2
    if jq -e '.success == true' "$trial_dir/trial.json" >/dev/null; then passed=$((passed + 1)); fi
    continue
  fi

  # Retry only invalid attempts; archive the earlier evidence, never delete it.
  if [ -d "$trial_dir" ]; then
    mkdir -p "$RUN_DIR/attempts/$slug"
    mv "$trial_dir" "$RUN_DIR/attempts/$slug/$(date +%s)-$$"
  fi
  mkdir -p "$trial_dir"

  if [ "$TASK_SOURCE" = repository-v1 ]; then
    if ! prepare_repo_task "$input_path" >"$trial_dir/prepare.log" 2>&1; then
      record_infra "task preparation failed; see prepare.log"
      invalid=$((invalid + 1))
      continue
    fi
  fi

  if [ "$PREPULL" -eq 1 ] && ! prepare_image >"$trial_dir/pull.log" 2>&1; then
    record_infra "task image pull failed"
    invalid=$((invalid + 1))
    continue
  fi

  printf '\n=== [%s] running locally: %s\n' "$entry" "$command" >&2
  started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  started=$(date +%s)
  exit_code=0
  (
    if [ "$TASK_SOURCE" = repository-v1 ]; then
      if [ "$suite" = datacurve ]; then
        export DOCKER_DEFAULT_PLATFORM="$TASK_PLATFORM"
      else
        # Harbor builds its egress sidecar for the native Docker daemon.
        unset DOCKER_DEFAULT_PLATFORM
      fi
    fi
    exec "$TIMEOUT_BIN" --kill-after=30 "$TIMEOUT" bash -c "$command"
  ) </dev/null >"$trial_dir/runner.log" 2>&1 || exit_code=$?
  duration=$(( $(date +%s) - started ))
  jq -n --argjson exit_code "$exit_code" --argjson duration "$duration" --argjson timeout "$TIMEOUT" \
    '{exit_code:$exit_code, duration_seconds:$duration, timeout_seconds:$timeout}' \
    > "$trial_dir/completion.json.tmp"
  mv "$trial_dir/completion.json.tmp" "$trial_dir/completion.json"

  # Same baseline collector rules as run-trials.sh: a skeleton record, then scoring
  # from authoritative leaf result evidence by calculate-cost.py.
  jq -n \
    --arg id "$entry" --arg task "$task" --arg suite "$suite" --arg started_at "$started_at" \
    --argjson duration "$duration" --argjson exit_code "$exit_code" \
    '{id:$id, title:$task, suite:$suite, status:"infra_invalid", success:false,
      duration_seconds:$duration, exit_code:$exit_code, started_at:$started_at,
      runtime:"local-docker",
      included_in_efficiency:false}' > "$trial_dir/trial.json.tmp"
  mv "$trial_dir/trial.json.tmp" "$trial_dir/trial.json"
  python3 "$SCRIPT_DIR/calculate-cost.py" --trial "$trial_dir" --model "$MODEL" --harness "$HARNESS" --score --write
  status=$(jq -r .status "$trial_dir/trial.json")
  if [ "$status" = infra_invalid ]; then invalid=$((invalid + 1)); fi
  success=$(jq -r .success "$trial_dir/trial.json")
  if [ "$success" = true ]; then passed=$((passed + 1)); fi
  printf '=== [%s] %s in %ss (exit %s)\n' "$entry" "$status" "$duration" "$exit_code" >&2
done < "$TASK_LIST"


echo >&2
echo "$passed/$total passed. Evidence in $RUN_DIR/trials/" >&2
echo "Next: node $(dirname "$0")/normalize-results.mjs --run $RUN_DIR --label \"$HARNESS\"" >&2

[ "$invalid" -eq 0 ] || exit 1
