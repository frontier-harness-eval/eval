#!/usr/bin/env bash
# Run MiniMax Code as Harbor's built-in `mcode` agent against the public task set.
set -euo pipefail

# shellcheck source=providers.sh
. "$(cd "$(dirname "$0")" && pwd)/providers.sh"

PROVIDER="fireworks"
MODEL=""
MCODE_VERSION="0.2.7"
CHECKPOINT=""
RUN_ID=""
TASKS=""
OUT="runs"
TIMEOUT="5400"
PRINT_COMMAND=0

usage() {
  cat <<EOF
Usage: run-minimax-code.sh --checkpoint NAME --run-id ID --tasks FILE [options]

Options:
  --provider NAME      Kimi K3 provider (default fireworks). One of:
                       fireworks moonshot openrouter together
  --model ID           Override the provider's Kimi K3 model route
  --out DIR            Root output directory (default runs)
  --timeout SEC        Per-task timeout (default 5400)
  --print-command      Print the rendered Harbor template and exit; no credentials or
                       Runta runtime are required

The golden checkpoint must contain pinned Terminal-Bench and DeepSWE assets overlaid
with this repository's public task definitions, plus the offline MCode runtime bundle.
Create it with provision-golden-checkpoint.sh --copy-tasks tasks. All task suites are
then executed through Harbor.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --checkpoint) CHECKPOINT=$2; shift 2 ;;
    --run-id) RUN_ID=$2; shift 2 ;;
    --tasks) TASKS=$2; shift 2 ;;
    --provider) PROVIDER=$2; shift 2 ;;
    --model) MODEL=$2; shift 2 ;;
    --out) OUT=$2; shift 2 ;;
    --timeout) TIMEOUT=$2; shift 2 ;;
    --print-command) PRINT_COMMAND=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if ! resolve_provider "$PROVIDER" || [ "$PROVIDER" = custom ]; then
  echo "unsupported --provider $PROVIDER; expected fireworks, moonshot, openrouter, or together" >&2
  exit 2
fi
MODEL=${MODEL:-$PROVIDER_MODEL}
warn_unless_kimi_k3 "$MODEL"
case "$MODEL" in
  ""|*[!A-Za-z0-9._:/+-]*) echo "invalid --model: $MODEL" >&2; exit 2 ;;
esac
case "$TIMEOUT" in
  ""|*[!0-9]*) echo "invalid --timeout: $TIMEOUT" >&2; exit 2 ;;
esac

# Harbor's MCode adapter registers an API-key provider in MCode. The shared provider
# resolver owns the protocol translation so generic and MCode routes cannot drift.
MCODE_MODEL="$PROVIDER_MCODE_PREFIX${MODEL#"$PROVIDER_MCODE_STRIP"}"
CONNECTION=$PROVIDER_MCODE_CONNECTION

COMMAND_PREFIX="env PYTHONPATH=/work${CONNECTION:+ $CONNECTION}"
BUNDLE_SHA='$(cat /work/evidence/mcode-bundle.sha256)'
AGENT_ARGS="-a frontierharness_mcode:OfflineMCode -m $MCODE_MODEL --ak version=$MCODE_VERSION --ak bundle_path=/work/mcode-runtime.tar.gz --ak bundle_sha256=$BUNDLE_SHA --ak api_format=openai-completions --allow-agent-host $PROVIDER_HOST --jobs-dir {jobs}"
TERMINAL_COMMAND="$COMMAND_PREFIX harbor run -p /work/terminal-bench/tasks --include-task-name {task} $AGENT_ARGS"
DATACURVE_COMMAND="$COMMAND_PREFIX harbor run -p /work/deep-swe/tasks --include-task-name {task} $AGENT_ARGS"

if [ "$PRINT_COMMAND" -eq 1 ]; then
  printf 'terminal-bench\t%s\n' "$TERMINAL_COMMAND"
  printf 'datacurve\t%s\n' "$DATACURVE_COMMAND"
  exit 0
fi

for required in CHECKPOINT RUN_ID TASKS; do
  if [ -z "${!required}" ]; then
    echo "missing --$(echo "$required" | tr 'A-Z_' 'a-z-')" >&2
    usage >&2
    exit 2
  fi
done

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
exec "$SCRIPT_DIR/run-trials.sh" \
  --checkpoint "$CHECKPOINT" \
  --harness mcode \
  --harness-version "$MCODE_VERSION" \
  --provider "$PROVIDER" \
  --model "$MCODE_MODEL" \
  --checkpoint-model "$MODEL" \
  --run-id "$RUN_ID" \
  --tasks "$TASKS" \
  --out "$OUT" \
  --timeout "$TIMEOUT" \
  --terminal-cmd "$TERMINAL_COMMAND" \
  --datacurve-cmd "$DATACURVE_COMMAND"
