#!/bin/sh
# One FrontierHarness trial with Alma as the harness. This is the --cmd template
# for the official run-trials.sh:
#
#   --cmd '/work/harness/eval/frontierharness/run-task.sh {suite} {task} {model} {jobs}'
#
# It dispatches to the official runner for the suite (Harbor for terminal-bench,
# Pier for datacurve/DeepSWE) with Alma's external-agent adapter, then writes a
# flat human-readable digest to {jobs}/00-summary/alma-summary.json. The runner's
# own documents are left untouched next to it, and the official scorer reads the
# runner's leaf result.json directly -- the digest must not be named result.json,
# because calculate-cost.py scores a trial infra_invalid when {jobs} contains
# more than one leaf result.json.
set -u
SUITE=$1; TASK=$2; MODEL=$3; JOBS=$4
HERE=$(cd "$(dirname "$0")" && pwd)
HARNESS_DIR=$(cd "$HERE/../.." && pwd)
export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
export ALMA_FH_HARNESS_DIR="$HARNESS_DIR"
export ALMA_FH_PORT="${ALMA_FH_PORT:-23100}"
export ALMA_FH_NODE_BIN="${ALMA_FH_NODE_BIN:-/work/alma/node-linux-x64}"
export ALMA_FH_LOG_DIR="${ALMA_FH_LOG_DIR:-/work/alma/logs}"

# Per-task agent budget, copied verbatim from the published
# tasks/<task>/task.toml of the eval repo ([agent] timeout_sec). The runner is
# given the task id, not the task file, so the contract is carried here where it
# can be audited against upstream. Alma used to run every task on a single flat
# ALMA_FH_TIMEOUT_SEC (5000). The second and third fields are the task's
# declared [environment] cpus / memory_mb, kept in the table for audit only: the
# official pipeline gives every trial the same 4 vCPU / 8 GiB runtime and does
# not read those keys, so neither does this runner.
case "$TASK" in
  anko-typed-variable-bindings)           DECL="5400 2 8192" ;;
  arktype-json-schema-refs-dependencies)  DECL="5400 2 8192" ;;
  build-cython-ext)                       DECL="900 1 2048" ;;
  chess-best-move)                        DECL="900 1 2048" ;;
  code-from-image)                        DECL="1200 1 2048" ;;
  constraints-scheduling)                 DECL="1200 1 2048" ;;
  db-wal-recovery)                        DECL="900 1 2048" ;;
  dna-insert)                             DECL="1800 1 4096" ;;
  expr-try-catch-errors)                  DECL="5400 2 8192" ;;
  extract-elf)                            DECL="900 1 2048" ;;
  fastapi-deprecation-response-headers)   DECL="5400 2 8192" ;;
  gcode-to-text)                          DECL="900 1 2048" ;;
  git-leak-recovery)                      DECL="900 1 2048" ;;
  httpx-multipart-response-parsing)       DECL="5400 2 8192" ;;
  katex-multicolumn-array-spans)          DECL="5400 2 8192" ;;
  kv-store-grpc)                          DECL="900 1 2048" ;;
  largest-eigenval)                       DECL="900 1 2048" ;;
  log-summary-date-ranges)                DECL="900 1 2048" ;;
  merge-diff-arc-agi-task)                DECL="900 1 4096" ;;
  meriyah-explicit-resource-declarations) DECL="5400 2 8192" ;;
  modernize-scientific-stack)             DECL="600 1 2048" ;;
  multi-source-data-merger)               DECL="900 1 2048" ;;
  openssl-selfsigned-cert)                DECL="900 1 2048" ;;
  polyglot-c-py)                          DECL="900 1 2048" ;;
  python-statemachine-state-data-scoping) DECL="5400 2 8192" ;;
  regex-log)                              DECL="1200 1 2048" ;;
  sanitize-git-repo)                      DECL="900 1 2048" ;;
  scc-bounded-memory-spilling)            DECL="5400 2 8192" ;;
  sqlite-db-truncate)                     DECL="1200 1 2048" ;;
  vulnerable-secret)                      DECL="900 1 2048" ;;
  *)
    echo "no declared budget for task '$TASK'; refusing to guess" >&2
    exit 64 ;;
esac
# shellcheck disable=SC2086
set -- $DECL
export ALMA_FH_TIMEOUT_SEC="$1"
# The wrap-up nudge Alma used to get 600 s before its deadline is an Alma-only
# affordance no published harness has; the run does not use it.
export ALMA_FH_STEER_LEAD_SEC=0
mkdir -p "$JOBS"

# Runta wraps runc (/usr/local/sbin/runc -> /opt/runta/runta-runc) to inject its own
# PID 1 into every container, and that init never exits once its child has: any
# short-lived container hangs (`docker run --rm img true` never returns), so every
# Dockerfile RUN step hangs under BuildKit and the classic builder alike. Pier's
# separate verifier environment builds tests/Dockerfile, which would sit in that
# hang until the 1800 s verifier timeout (README deviation 10). Point the daemon's
# runc at the real binary; the egress CA the wrapper used to mount is supplied by
# /work/runta-ca-overlay.yaml for Harbor, and DeepSWE containers have no network.
if [ "$(readlink /usr/local/sbin/runc 2>/dev/null)" = /opt/runta/runta-runc ]; then
  ln -sfn /usr/bin/runc /usr/local/sbin/runc
fi

# Bring Alma up before the runner starts its clock (agent setup has its own,
# shorter, timeout).
node "$HERE/alma-drive.mjs" ensure-server --port "$ALMA_FH_PORT" >"$JOBS/alma-ensure.log" 2>&1 || {
  echo "alma server failed to start; see $JOBS/alma-ensure.log" >&2
  cat "$JOBS/alma-ensure.log" >&2
  exit 70
}

case "$SUITE" in
  terminal-bench)
    OVERLAY=""
    [ -f /work/runta-ca-overlay.yaml ] && OVERLAY="--extra-docker-compose /work/runta-ca-overlay.yaml"
    # shellcheck disable=SC2086
    harbor run -d terminal-bench@2.0 -i "$TASK" -a alma_harbor_agent:AlmaAgent -m "$MODEL" \
      --jobs-dir "$JOBS" $OVERLAY -r 2 -y
    rc=$? ;;
  datacurve)
    # The official template passes --output-dir, which datacurve-pier 0.3.1 does not
    # have (its flag is --jobs-dir / -o).
    pier run -p "/work/deep-swe/tasks/$TASK" --agent-import-path alma_pier_agent:AlmaAgent --model "$MODEL" \
      --jobs-dir "$JOBS" -y
    rc=$? ;;
  *)
    echo "unknown suite: $SUITE" >&2
    exit 64 ;;
esac

python3 "$HERE/alma_fh_common.py" summarize "$JOBS" >/dev/null 2>"$JOBS/summarize.err" || echo "summary failed; see $JOBS/summarize.err" >&2
# Evidence: Alma's own server log and the proxy's per-request usage log.
mkdir -p "$JOBS/00-summary"
cp "$ALMA_FH_LOG_DIR"/alma-server.log "$JOBS/00-summary/" 2>/dev/null || true
cp "$ALMA_FH_LOG_DIR"/fw-usage.jsonl "$JOBS/00-summary/" 2>/dev/null || true
cp "$ALMA_FH_LOG_DIR"/fw-proxy.log "$JOBS/00-summary/" 2>/dev/null || true
exit $rc
