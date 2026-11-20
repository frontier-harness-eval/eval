# The local runner and doctor accept a workspace task directory or subset file.
list_task_ids() {
  local input=$1 toml
  if [ -d "$input" ]; then
    for toml in "$input"/*/task.toml; do
      [ -r "$toml" ] || continue
      awk -F'"' '/^\[/ { in_task = ($0 == "[task]") }
                 in_task && /^name *=/ { print $2; exit }' "$toml"
    done | sort -u
  elif [ -f "$input" ]; then
    awk '{ sub(/#.*/, ""); gsub(/^[[:space:]]+|[[:space:]]+$/, ""); if (length) print }' "$input"
  else
    echo "cannot read task list: $input" >&2
    return 1
  fi
}

prepare_repo_task() {
  local authority=tasks
  [ ! -d "$TASKS" ] || authority=$TASKS
  python3 "$SCRIPT_DIR/task_inputs.py" "$entry" "$1" --repo-tasks "$authority" \
    --deep-swe "${DEEP_SWE:-.fh-local/deep-swe}"
}

# Build the command for the suite on the local Docker host.
repository_command() {
  local suite=$1 task_path=$2 harness=$3 model=$4 jobs=$5 mounts
  local args use_dsh=0
  if [ "$suite" = terminal-bench ]; then
    # Harbor's -a accepts a registered name or a module.path:ClassName import path.
    local agent=${HARBOR_AGENT_IMPORT_PATH:-$harness}
    if [ "$BUNDLED_DSH" = 1 ] && [ -z "$HARBOR_AGENT_IMPORT_PATH" ]; then
      agent=adapters.dsh.agent:DeepSeekHarness
      use_dsh=1
    fi
    args=(harbor run -p "$task_path" -a "$agent" -m "$model" --jobs-dir "$jobs" -r "$HARBOR_RETRIES" -y)
    local allowed host=${SECRET_HOST:-$PROVIDER_HOST}
    if [ -n "$host" ]; then
      args+=(--allow-agent-host "$host")
      # Harbor installs Codex with nvm in Debian/Ubuntu task images.
      if [ "$agent" = codex ]; then args+=(--allow-environment-host nodejs.org); fi
      while IFS= read -r allowed; do
        [ "$allowed" = "$host" ] || args+=(--allow-environment-host "$allowed")
      done < <(provider_egress_policy "$host" | jq -r '.allowed_hosts[]')
    fi
    if [ "${task_path##*/}" = build-cython-ext ]; then
      mounts=$(jq -cn --arg src "$task_path/pyknotid.bundle" \
        '[{type:"bind",source:$src,target:"/app/pyknotid.bundle",read_only:true}]')
      args+=(--mounts "$mounts")
    fi
  elif [ "$suite" = datacurve ]; then
    # Pier's --agent only accepts its built-in names; anything else needs an
    # adapter class loaded with --agent-import-path.
    if [ -n "${PIER_AGENT_IMPORT_PATH:-}" ]; then
      args=(pier run -p "$task_path" --agent-import-path "$PIER_AGENT_IMPORT_PATH")
    elif [ "$BUNDLED_DSH" = 1 ]; then
      args=(pier run -p "$task_path" --agent-import-path adapters.dsh.pier_agent:DeepSeekHarness)
      use_dsh=1
    else
      args=(pier run -p "$task_path" --agent "$harness")
    fi
    args+=(--model "$model" --jobs-dir "$jobs" -y)
  else
    echo "Unknown suite $suite; pass --cmd for a custom runner" >&2
    return 2
  fi
  if [ "$use_dsh" = 1 ]; then
    args+=(--agent-kwarg "base_url=$BASE_URL" --agent-kwarg "secret_name=$SECRET_NAME" --agent-kwarg "platform=$TASK_PLATFORM"
           --agent-kwarg "harness=$harness" --agent-kwarg "api=$DSH_API")
    if [ -n "$DSH_SEARCH" ]; then args+=(--agent-kwarg "web_search_max_keywords=$DSH_SEARCH"); fi
  elif [ -n "$SECRET_NAME" ] && { [ "$suite" = datacurve ] || [ -z "$BASE_URL" ] || [ "$BUNDLED_DSH" = 1 ]; }; then
    # Both runners resolve the literal reference at agent setup. Job configs and
    # process arguments contain variable names only.
    args+=(--agent-env "$SECRET_NAME=\${$SECRET_NAME}")
    if [ "$PROVIDER" = fireworks ]; then args+=(--agent-env "FIREWORKS_AI_API_KEY=\${$SECRET_NAME}"); fi
  fi
  printf '%q ' "${args[@]}"
}

# Concurrent suite lanes can initialize one run. Publish a complete manifest
# once, then let every caller validate the winning configuration.
publish_manifest() {
  local target=$1 tmp
  tmp=$(mktemp "$target.XXXXXX") || return 1
  if ! cat > "$tmp" || ! jq -e . "$tmp" >/dev/null; then rm -f "$tmp"; return 1; fi
  if ! ln "$tmp" "$target" 2>/dev/null && [ ! -f "$target" ]; then rm -f "$tmp"; return 1; fi
  rm -f "$tmp"
}

task_catalog_digest() {
  [ "$TASK_SOURCE" = repository-v1 ] || return 0
  local authority=tasks
  [ ! -d "$TASKS" ] || authority=$TASKS
  python3 - "$authority" <<'PY'
import hashlib
from pathlib import Path
import sys

digest = hashlib.sha256()
for task in sorted(Path(sys.argv[1]).glob("*/task.toml")):
    for path in (task, task.with_name("instruction.md")):
        digest.update(str(path.relative_to(task.parent.parent)).encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
print(digest.hexdigest())
PY
}

# Keep the lock on the controller's open file description until the next task
# or process exit. Different suites may still share a run concurrently.
lock_trial() {
  mkdir -p "$RUN_DIR/.task-locks"
  exec 8>"$RUN_DIR/.task-locks/$slug"
  python3 - "$entry" <<'PYLOCK'
import fcntl
import sys

try:
    fcntl.flock(8, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    sys.exit(f"Another controller is running {sys.argv[1]} with this run ID")
PYLOCK
}
