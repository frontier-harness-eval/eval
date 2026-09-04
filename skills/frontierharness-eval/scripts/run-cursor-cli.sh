#!/usr/bin/env bash
# Run the benchmark through Cursor's headless CLI using the `cursor-cli` agent that
# Harbor and Pier both ship. A thin wrapper over run-trials.sh: it fixes the provider and
# harness, hands Kimi K3 token prices to Harbor's adapter, splits the two suites so each
# gets its own runner template, and checks the CLI version was the same in every trial.
# Background and caveats: ../cursor-cli.md
set -euo pipefail

FH=$(cd "$(dirname "$0")" && pwd)

CHECKPOINT=""
RUN_ID=""
TASKS="tasks"
OUT="runs"
TIMEOUT=5400
TOKEN_RATE=0
PRINT_ONLY=0

usage() {
  cat <<EOF
Usage: run-cursor-cli.sh --checkpoint NAME --run-id ID [--tasks PATH] [--out DIR]
                         [--timeout SEC] [--cursor-token-rate USD_PER_M] [--print-command]

  --tasks PATH             Task directory or list file, exactly as run-trials.sh takes it
  --out DIR                Root output directory (default runs)
  --timeout SEC            Per-task timeout (default 5400)
  --cursor-token-rate N    Cursor Token Rate in USD per million tokens, added to every
                           rate below. Cursor lists 0.25 for Teams and Enterprise plans
                           and none for individual plans. Default 0.
  --print-command          Render the Harbor template and exit; needs no credentials

Terminal-Bench tasks run through Harbor with Kimi K3 list prices passed to the cursor-cli
adapter, since Harbor has no built-in rate for kimi-k3. DeepSWE tasks run through Pier's
cursor-cli adapter, which takes no pricing override, so their cost field stays empty and
must be joined from Cursor's usage data if it is reported at all. See cursor-cli.md.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --checkpoint) CHECKPOINT=$2; shift 2 ;;
    --run-id) RUN_ID=$2; shift 2 ;;
    --tasks) TASKS=$2; shift 2 ;;
    --out) OUT=$2; shift 2 ;;
    --timeout) TIMEOUT=$2; shift 2 ;;
    --cursor-token-rate) TOKEN_RATE=$2; shift 2 ;;
    --print-command) PRINT_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$TOKEN_RATE" in
  ''|*[!0-9.]*|*.*.*) echo "--cursor-token-rate must be a non-negative decimal" >&2; exit 2 ;;
esac

# Kimi K3 on Cursor's pricing page: $3 input, $0.30 cache read, $15 output per million,
# no cache-write line. cacheWriteTokens are still input tokens the provider processed, so
# they are priced at the input rate, which is also what Harbor does when the key is
# omitted; it is written out so the rate in the evidence is explicit.
rate() { awk -v base="$1" -v extra="$TOKEN_RATE" 'BEGIN { printf "%g", base + extra }'; }
PRICING=$(printf '{"input":%s,"output":%s,"cache_read":%s,"cache_write":%s}' \
  "$(rate 3)" "$(rate 15)" "$(rate 0.3)" "$(rate 3)")

# The default Terminal-Bench template from run-trials.sh, plus the pricing kwarg.
# run-trials.sh has no way to append to its default, so the template is restated here;
# keep it in step with default_cmd() there.
HARBOR_CMD="harbor run -d terminal-bench@2.0 -i {task} -a {harness} -m {model} --jobs-dir {jobs} --extra-docker-compose /work/runta-ca-overlay.yaml -r 2 -y --ak pricing='$PRICING'"

if [ "$PRINT_ONLY" -eq 1 ]; then
  echo "$HARBOR_CMD"
  exit 0
fi

for required in CHECKPOINT RUN_ID; do
  if [ -z "${!required}" ]; then
    echo "missing --$(echo "$required" | tr 'A-Z_' 'a-z-')" >&2
    usage >&2
    exit 2
  fi
done

# Split the task set by suite so each half gets its runner template. Reads the same two
# shapes run-trials.sh accepts: a directory of task.toml files, or a list file.
ALL=$(mktemp); TB=$(mktemp); DS=$(mktemp)
trap 'rm -f "$ALL" "$TB" "$DS"' EXIT
if [ -d "$TASKS" ]; then
  for toml in "$TASKS"/*/task.toml; do
    [ -r "$toml" ] || continue
    awk -F'"' '/^\[/ { in_task = ($0 == "[task]") }
               in_task && /^name *=/ { print $2; exit }' "$toml"
  done | sort -u > "$ALL"
elif [ -r "$TASKS" ]; then
  tr -d '\r' < "$TASKS" | sed 's/#.*//; s/^ *//; s/ *$//' | grep -v '^$' > "$ALL" || true
else
  echo "cannot read task list: $TASKS" >&2
  exit 1
fi
grep '^terminal-bench/' "$ALL" > "$TB" || true
grep '^datacurve/' "$ALL" > "$DS" || true
[ -s "$TB" ] || [ -s "$DS" ] || { echo "no tasks found in $TASKS" >&2; exit 1; }

common=(--checkpoint "$CHECKPOINT" --harness cursor-cli --provider cursor
        --run-id "$RUN_ID" --out "$OUT" --timeout "$TIMEOUT")

if [ -s "$TB" ]; then
  "$FH/run-trials.sh" "${common[@]}" --tasks "$TB" --cmd "$HARBOR_CMD"
fi
if [ -s "$DS" ]; then
  "$FH/run-trials.sh" "${common[@]}" --tasks "$DS"
fi

# Both adapters install the CLI inside the task container at trial time from Cursor's
# installer, so nothing pins its version. A run is one configuration only if every trial
# reports the same version; anything else is two harness versions in one row.
versions=$(find "$OUT/$RUN_ID/trials" -name '*.json' -size -8M 2>/dev/null \
  | xargs -r jq -r '.. | objects | select(has("agent_info")) | .agent_info.version? // empty' 2>/dev/null \
  | sort -u)
case "$(printf '%s\n' "$versions" | grep -c .)" in
  0) echo "warning: no agent_info.version found in the collected jobs; record the CLI version by hand" >&2 ;;
  1) echo "cursor-agent version across all trials: $versions" >&2 ;;
  *) echo "warning: more than one cursor-agent version in this run; it is not one configuration:" >&2
     printf '  %s\n' $versions >&2 ;;
esac
