#!/usr/bin/env bash
# Offline checks for the graff evaluation profile. No Runta credentials required.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
FH="$ROOT/skills/frontierharness-eval/scripts"
cd "$ROOT"

fail() { echo "FAIL: $*" >&2; exit 1; }

bash -n "$FH/install-graff.sh"
bash -n "$FH/run-graff.sh"
bash -n "$FH/run-trials.sh"
bash -n "$FH/provision-golden-checkpoint.sh"
bash -n "$ROOT/skills/frontierharness-eval/tests/test-graff.sh"

python3 - <<'PY'
import ast
from pathlib import Path
root = Path("skills/frontierharness-eval/agents")
for name in ("frontierharness_graff.py", "frontierharness_graff_pier.py"):
    ast.parse((root / name).read_text(), filename=name)
print("ast.parse ok")
PY

out=$("$FH/run-graff.sh" --print-command)
printf '%s\n' "$out" | grep -q 'frontierharness_graff:Graff' \
  || fail "Harbor template missing frontierharness_graff:Graff"
printf '%s\n' "$out" | grep -q 'frontierharness_graff_pier:Graff' \
  || fail "Pier template missing frontierharness_graff_pier:Graff"
printf '%s\n' "$out" | grep -q 'terminal-bench@2.0' \
  || fail "Harbor template missing terminal-bench@2.0"
printf '%s\n' "$out" | grep -q '/work/deep-swe/tasks/{task}' \
  || fail "Pier template missing deep-swe task path"
printf '%s\n' "$out" | grep -q 'binary_path=/work/graff/graff' \
  || fail "templates missing checkpointed binary path"

if "$FH/run-graff.sh" --provider together --print-command >/dev/null 2>&1; then
  fail "together should be rejected"
fi
if "$FH/run-graff.sh" --provider custom --print-command >/dev/null 2>&1; then
  fail "custom should be rejected"
fi

"$FH/run-trials.sh" --help | grep -q -- '--terminal-cmd' \
  || fail "run-trials.sh --help missing --terminal-cmd"
"$FH/run-trials.sh" --help | grep -q -- '--datacurve-cmd' \
  || fail "run-trials.sh --help missing --datacurve-cmd"

grep -q '2098a13099ee9a645a5a535d04fe5fd8f2602181a93542a3e4b1498ba28474d8' \
  "$ROOT/skills/frontierharness-eval/graff.md" \
  || fail "graff.md missing x86_64 digest"
grep -q '68540a541e13dac127c7bb4523f77f736601b186' \
  "$ROOT/skills/frontierharness-eval/graff.md" \
  || fail "graff.md missing commit pin"

echo "ok"
