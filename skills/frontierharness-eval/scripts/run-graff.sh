#!/usr/bin/env bash
# Run graff as a custom Harbor/Pier agent against the public task set.
set -euo pipefail

# shellcheck source=providers.sh
. "$(cd "$(dirname "$0")" && pwd)/providers.sh"

PROVIDER="fireworks"
MODEL=""
CHECKPOINT=""
RUN_ID=""
TASKS=""
OUT="runs"
TIMEOUT="5400"
PRINT_COMMAND=0

usage() {
  cat <<USAGE
Usage: run-graff.sh --checkpoint NAME --run-id ID [options]

Options:
  --provider NAME      Kimi K3 provider (default fireworks). One of:
                       fireworks moonshot openrouter
  --model ID           Override the provider's Kimi K3 model route
  --tasks FILE         Suite-prefixed task list (default: published tasks/)
  --out DIR            Root output directory (default runs)
  --timeout SEC        Per-task timeout (default 5400)
  --print-command      Print the rendered Harbor and Pier templates and exit;
                       no credentials or Runta runtime are required
USAGE
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

if ! resolve_provider "$PROVIDER" || [ "$PROVIDER" = custom ] || [ "$PROVIDER" = together ]; then
  echo "unsupported --provider $PROVIDER; expected fireworks, moonshot, or openrouter" >&2
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

COMMAND_PREFIX="env PYTHONPATH=/work"
AGENT_ARGS="-a frontierharness_graff:Graff -m {model} --ak binary_path=/work/graff/graff --jobs-dir {jobs} --extra-docker-compose /work/runta-ca-overlay.yaml -r 2 -y"
TERMINAL_COMMAND="$COMMAND_PREFIX harbor run -d terminal-bench@2.0 -i {task} $AGENT_ARGS"
DATACURVE_COMMAND="$COMMAND_PREFIX pier run -p /work/deep-swe/tasks/{task} --agent-import-path frontierharness_graff_pier:Graff --model {model} --agent-kwarg binary_path=/work/graff/graff --output-dir {jobs}"

if [ "$PRINT_COMMAND" -eq 1 ]; then
  printf 'terminal-bench\t%s\n' "$TERMINAL_COMMAND"
  printf 'datacurve\t%s\n' "$DATACURVE_COMMAND"
  exit 0
fi

if [ -z "$CHECKPOINT" ] || [ -z "$RUN_ID" ]; then
  echo "missing --checkpoint or --run-id" >&2
  usage >&2
  exit 2
fi

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
args=(
  --checkpoint "$CHECKPOINT"
  --harness graff
  --provider "$PROVIDER"
  --model "$MODEL"
  --run-id "$RUN_ID"
  --out "$OUT"
  --timeout "$TIMEOUT"
  --terminal-cmd "$TERMINAL_COMMAND"
  --datacurve-cmd "$DATACURVE_COMMAND"
)
if [ -n "$TASKS" ]; then
  args+=(--tasks "$TASKS")
fi
exec "$SCRIPT_DIR/run-trials.sh" "${args[@]}"
