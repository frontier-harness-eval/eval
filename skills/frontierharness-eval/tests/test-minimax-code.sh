#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
RUNNER="$ROOT/scripts/run-minimax-code.sh"
PROVISIONER="$ROOT/scripts/provision-golden-checkpoint.sh"
RUN_TRIALS="$ROOT/scripts/run-trials.sh"

assert_contains() {
  case "$1" in
    *"$2"*) ;;
    *) echo "expected command to contain: $2" >&2; exit 1 ;;
  esac
}

bash -n "$RUNNER" "$PROVISIONER"
python3 -c 'import ast, pathlib, sys; ast.parse(pathlib.Path(sys.argv[1]).read_text())' \
  "$ROOT/agents/frontierharness_mcode.py"

fireworks=$($RUNNER --provider fireworks --print-command)
assert_contains "$fireworks" 'OPENAI_API_KEY="$FIREWORKS_API_KEY"'
assert_contains "$fireworks" 'OPENAI_BASE_URL="https://api.fireworks.ai/inference/v1"'
assert_contains "$fireworks" '-m openai/accounts/fireworks/models/kimi-k3'
assert_contains "$fireworks" '-p /work/terminal-bench/tasks --include-task-name {task}'
case "$fireworks" in
  *@latest*) echo "Terminal-Bench must use an immutable content digest" >&2; exit 1 ;;
esac
assert_contains "$fireworks" '-p /work/deep-swe/tasks'
assert_contains "$fireworks" '--ak version=0.2.7'
assert_contains "$fireworks" '-a frontierharness_mcode:OfflineMCode'
assert_contains "$fireworks" 'PYTHONPATH=/work'
assert_contains "$fireworks" '--ak bundle_path=/work/mcode-runtime.tar.gz'
assert_contains "$fireworks" '--allow-agent-host api.fireworks.ai'
assert_contains "$(cat "$PROVISIONER")" 'terminal-bench/terminal-bench-2-1@sha256:7d7bdc1cbedad549fc1140404bd4dc45e5fd0ea7c4186773687d177ad3a0699a'

moonshot=$($RUNNER --provider moonshot --print-command)
assert_contains "$moonshot" 'OPENAI_API_KEY="$MOONSHOT_API_KEY"'
assert_contains "$moonshot" '-m openai/kimi-k3'

openrouter=$($RUNNER --provider openrouter --print-command)
assert_contains "$openrouter" '-m openrouter/moonshotai/kimi-k3'
case "$openrouter" in
  *OPENAI_API_KEY*) echo "OpenRouter command unexpectedly remapped its credential" >&2; exit 1 ;;
esac

together=$($RUNNER --provider together --print-command)
assert_contains "$together" '-m together/moonshotai/Kimi-K3'
assert_contains "$together" '--ak version=0.2.7'

if $RUNNER --provider custom --print-command >/dev/null 2>&1; then
  echo "custom provider should require the generic --cmd path" >&2
  exit 1
fi

if $RUNNER --mcode-version 0.2.6 --print-command >/dev/null 2>&1; then
  echo "the pinned profile should reject MCode version overrides" >&2
  exit 1
fi

if $RUNNER --model 'openai/kimi-k3;false' --print-command >/dev/null 2>&1; then
  echo "unsafe model route should be rejected" >&2
  exit 1
fi

if $RUNNER --timeout '30;false' --print-command >/dev/null 2>&1; then
  echo "unsafe timeout should be rejected" >&2
  exit 1
fi

if RUNTA_TOKEN=x FIREWORKS_API_KEY=x "$PROVISIONER" \
  --runtime test --checkpoint test --harness test --repo https://example.test/repo \
  >/dev/null 2>&1; then
  echo "--repo without --commit should be rejected" >&2
  exit 1
fi

# Exercise the real wrapper-to-run-trials boundary with a fake Runta CLI. The runner
# may fail the mock trials, but each suite must receive its own Harbor source.
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"
cat > "$TMP/bin/runta" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$RUNTA_LOG"
case "$1" in
  exec) exit 0 ;;
  cp)
    case "${2:-}" in
      fh-*:/work/manifest.json)
        mkdir -p "$(dirname "$3")"
        case "$2" in
          fh-test-*|fh-identity-mismatch-*)
            printf '%s\n' '{"harness":"mcode","harness_version":"0.2.7","model":"fireworks_ai/accounts/fireworks/models/kimi-k3","provider":"fireworks","task_count":30,"terminal_bench_overlay_count":21,"deep_swe_overlay_count":9,"terminal_bench_dataset":"terminal-bench/terminal-bench-2-1@sha256:7d7bdc1cbedad549fc1140404bd4dc45e5fd0ea7c4186773687d177ad3a0699a","tasks_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","terminal_bench_tasks_sha256":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd","deep_swe_tasks_sha256":"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee","deep_swe_commit":"435ee89ec2f2e2289f33b0da4f992f0b7b7266b9","mcode_bundle_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","mcode_agent_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}' > "$3"
            ;;
          fh-version-mismatch-*)
            printf '%s\n' '{"harness":"nop","harness_version":"0.2.7","model":"fireworks_ai/accounts/fireworks/models/kimi-k3","provider":"fireworks"}' > "$3"
            ;;
          *) printf '%s\n' '{"harness":"nop","harness_version":"","model":"fireworks_ai/accounts/fireworks/models/kimi-k3","provider":"fireworks"}' > "$3" ;;
        esac
        exit 0
        ;;
      *:/work/evidence/checkpoint-identity.json)
        mkdir -p "$(dirname "$3")"
        case "$2" in
          fh-identity-mismatch-*) tasks_sha256=ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff ;;
          *) tasks_sha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa ;;
        esac
        printf '%s\n' "{\"tasks_sha256\":\"$tasks_sha256\",\"terminal_bench_tasks_sha256\":\"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd\",\"deep_swe_tasks_sha256\":\"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee\",\"deep_swe_commit\":\"435ee89ec2f2e2289f33b0da4f992f0b7b7266b9\",\"mcode_bundle_sha256\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"mcode_agent_sha256\":\"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc\"}" > "$3"
        exit 0
        ;;
      *:/work/jobs/*)
        mkdir -p "$3"
        case "$2" in
          *anko-typed-variable-bindings*)
            printf '%s\n' '{"trials":[{"exception_info":{"exception_type":"AgentError"},"verifier_result":{"rewards":{"reward":1.0}}}]}' > "$3/result.json"
            ;;
          *)
            printf '%s\n' '{"reward_stats":{"reward":{"1.0":["trial"]}},"trials":[{"exception_info":null,"verifier_result":{"rewards":{"reward":1.0}}}]}' > "$3/result.json"
            ;;
        esac
        exit 0
        ;;
    esac
    exit 0
    ;;
  *) exit 0 ;;
esac
MOCK
chmod +x "$TMP/bin/runta"
printf '%s\n' terminal-bench/regex-log datacurve/anko-typed-variable-bindings > "$TMP/tasks.txt"

: > "$TMP/runta.log"
RUNTA_LOG="$TMP/runta.log" RUNTA_TOKEN=test FIREWORKS_API_KEY=test PATH="$TMP/bin:$PATH" \
  "$PROVISIONER" --runtime test --checkpoint test --harness mcode \
  --harness-version 0.2.7 --harbor-version 0.22.0 --harbor-only \
  --copy-tasks "$ROOT/../../tasks" >/dev/null 2>&1
provision_log=$(cat "$TMP/runta.log")
assert_contains "$provision_log" 'frontierharness_mcode.py'
assert_contains "$provision_log" 'node-v22.23.2-linux-x64.tar.gz'
assert_contains "$provision_log" "@minimax-ai/code@0.2.7"
assert_contains "$provision_log" 'terminal-bench/terminal-bench-2-1@sha256:7d7bdc1cbedad549fc1140404bd4dc45e5fd0ea7c4186773687d177ad3a0699a'

printf '%s\n' 'terminal-bench/regex-log;false' > "$TMP/unsafe-tasks.txt"
if RUNTA_LOG="$TMP/runta.log" RUNTA_TOKEN=test PATH="$TMP/bin:$PATH" \
  "$RUN_TRIALS" --checkpoint test --harness nop --run-id unsafe-task \
  --tasks "$TMP/unsafe-tasks.txt" --out "$TMP/unsafe-runs" >/dev/null 2>&1; then
  echo "unsafe task ID should be rejected" >&2
  exit 1
fi

RUNTA_LOG="$TMP/runta.log" RUNTA_TOKEN=test PATH="$TMP/bin:$PATH" \
  "$RUNNER" --checkpoint test --run-id test --tasks "$TMP/tasks.txt" \
  --out "$TMP/runs" >/dev/null 2>&1

assert_contains "$(cat "$TMP/runta.log")" '-p /work/terminal-bench/tasks --include-task-name regex-log'
assert_contains "$(cat "$TMP/runs/test/run.json")" '"harness_version": "0.2.7"'
jq -e '(.terminal_command_sha256 | test("^[0-9a-f]{64}$")) and
       (.datacurve_command_sha256 | test("^[0-9a-f]{64}$")) and
       (has("terminal_command_template") | not) and
       (has("datacurve_command_template") | not)' "$TMP/runs/test/run.json" >/dev/null
assert_contains "$(cat "$TMP/runta.log")" '-p /work/deep-swe/tasks --include-task-name anko-typed-variable-bindings'
jq -e '.status == "success" and .success == true' \
  "$TMP/runs/test/trials/terminal-bench-regex-log/trial.json" >/dev/null
jq -e '.status == "failure" and .success == false and .exception_info.exception_type == "AgentError"' \
  "$TMP/runs/test/trials/datacurve-anko-typed-variable-bindings/trial.json" >/dev/null

: > "$TMP/runta.log"
printf '%s\n' terminal-bench/regex-log > "$TMP/terminal-tasks.txt"
RUNTA_LOG="$TMP/runta.log" RUNTA_TOKEN=test PATH="$TMP/bin:$PATH" \
  "$RUNNER" --checkpoint test --run-id identity-mismatch \
  --tasks "$TMP/terminal-tasks.txt" --out "$TMP/identity-runs" >/dev/null 2>&1
jq -e '.status == "infra_invalid" and .error == "checkpoint manifest mismatch or incomplete task assets"' \
  "$TMP/identity-runs/identity-mismatch/trials/terminal-bench-regex-log/trial.json" >/dev/null

RUNTA_LOG="$TMP/runta.log" RUNTA_TOKEN=test PATH="$TMP/bin:$PATH" \
  "$RUN_TRIALS" --checkpoint test --harness nop --harness-version 0.2.6 \
  --run-id version-mismatch --tasks "$TMP/terminal-tasks.txt" \
  --out "$TMP/mismatch-runs" >/dev/null 2>&1
jq -e '.status == "infra_invalid" and .error == "checkpoint manifest mismatch or incomplete task assets"' \
  "$TMP/mismatch-runs/version-mismatch/trials/terminal-bench-regex-log/trial.json" >/dev/null

RUNTA_LOG="$TMP/runta.log" RUNTA_TOKEN=test PATH="$TMP/bin:$PATH" \
  "$RUN_TRIALS" --checkpoint test --harness nop --provider moonshot \
  --run-id provider-mismatch --tasks "$TMP/terminal-tasks.txt" \
  --out "$TMP/provider-runs" >/dev/null 2>&1
jq -e '.status == "infra_invalid" and .error == "checkpoint manifest mismatch or incomplete task assets"' \
  "$TMP/provider-runs/provider-mismatch/trials/terminal-bench-regex-log/trial.json" >/dev/null

: > "$TMP/runta.log"
RUNTA_LOG="$TMP/runta.log" RUNTA_TOKEN=test PATH="$TMP/bin:$PATH" \
  "$RUN_TRIALS" --checkpoint test --harness nop --run-id default-template \
  --tasks "$TMP/terminal-tasks.txt" --out "$TMP/default-runs" >/dev/null 2>&1
assert_contains "$(cat "$TMP/runta.log")" 'terminal-bench/terminal-bench-2-1@sha256:7d7bdc1cbedad549fc1140404bd4dc45e5fd0ea7c4186773687d177ad3a0699a --include-task-name terminal-bench/regex-log'

if RUNTA_LOG="$TMP/runta.log" RUNTA_TOKEN=test PATH="$TMP/bin:$PATH" \
  "$RUN_TRIALS" --checkpoint different --harness nop --run-id default-template \
  --tasks "$TMP/terminal-tasks.txt" --out "$TMP/default-runs" >/dev/null 2>&1; then
  echo "an existing run ID should reject mixed immutable configuration" >&2
  exit 1
fi

if RUNTA_LOG="$TMP/runta.log" RUNTA_TOKEN=test PATH="$TMP/bin:$PATH" \
  "$RUN_TRIALS" --checkpoint test --harness nop --run-id default-template \
  --tasks "$TMP/terminal-tasks.txt" --out "$TMP/default-runs" --timeout 60 \
  >/dev/null 2>&1; then
  echo "an existing run ID should reject a different timeout" >&2
  exit 1
fi

echo "MiniMax Code profile tests passed"
