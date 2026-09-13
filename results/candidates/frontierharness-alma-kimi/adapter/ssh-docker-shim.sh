#!/usr/bin/env bash
# ssh → docker-exec shim for the Alma container-benchmark runner.
#
# Point a headless Alma instance's ALMA_SSH_BIN at this script. Then any
# `ssh <target> <cmd>` Alma issues for a remote workspace whose target starts
# with $BENCH_PREFIX (default "bench-") is translated into `docker exec`
# against that container — so Alma's whole remote-workspace stack runs inside
# the task container with no sshd. DOCKER_HOST selects where the container
# lives (e.g. ssh://macmini to keep compute off this box). Any other target
# falls through to the real ssh.
#
#   ALMA_SSH_BIN=/abs/path/to/eval/ssh-docker-shim.sh
#   DOCKER_HOST=ssh://macmini            # optional; default = local docker
#   BENCH_PREFIX=bench-                  # must match the runner's --prefix
REAL_SSH="${BENCH_REAL_SSH:-/usr/bin/ssh}"
# An explicitly EMPTY prefix means "every ssh target is a container" (the
# FrontierHarness adapter runs Alma on a host whose only ssh targets are
# Harbor/Pier task containers); only an unset variable falls back to bench-.
PREFIX="${BENCH_PREFIX-bench-}"
args=("$@"); target=""; cmd=(); i=0; n=${#args[@]}
while [ $i -lt $n ]; do
  a="${args[$i]}"
  case "$a" in
    -o|-p|-i|-l|-F|-E) i=$((i+2)); continue ;;   # option that takes a value
    -*) i=$((i+1)); continue ;;                   # valueless flag
    *) if [ -z "$target" ]; then target="$a"; else cmd+=("$a"); fi; i=$((i+1)) ;;
  esac
done
case "$target" in
  "$PREFIX"*)
    if [ ${#cmd[@]} -eq 0 ]; then exec docker exec -i "$target" sh -l; fi
    exec docker exec -i "$target" sh -c "${cmd[*]}"
    ;;
  *) exec "$REAL_SSH" "$@" ;;
esac
