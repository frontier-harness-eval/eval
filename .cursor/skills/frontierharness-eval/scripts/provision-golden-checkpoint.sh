#!/usr/bin/env bash
# Provision a clean Runta runtime, install the FrontierHarness benchmark stack and the
# harness under evaluation, then freeze the result as a golden checkpoint.
set -euo pipefail

RUNTIME=""
CHECKPOINT=""
HARNESS=""
REPO=""
COMMIT=""
MODEL=""
SECRET_NAME=""
INSTALL_SCRIPT=""
PREPULL_TASKS=""
CPUS=4
MEMORY=8192
DEEP_SWE_REF="main"
KEEP_RUNTIME=0

usage() {
  cat <<'EOF'
Usage: provision-golden-checkpoint.sh --runtime NAME --checkpoint NAME --harness NAME
                                      --repo URL --commit SHA --model ID [options]

Required:
  --runtime NAME        Name for the build runtime (deleted unless --keep-runtime)
  --checkpoint NAME     Name for the golden checkpoint
  --harness NAME        Harness identifier used in reports, e.g. my-harness
  --repo URL            GitHub repo of the harness under evaluation
  --commit SHA          Commit to pin the harness to
  --model ID            Model identifier passed to the runner, e.g. moonshot/kimi-k3

Options:
  --secret-name NAME    Env var holding the provider key; stored as a Runta secret stub
  --install-script PATH Local script uploaded and run inside /work/harness to build it
  --prepull-tasks DIR   Directory of <task>/task.toml files whose images are pre-pulled
  --cpus N              vCPUs (default 4)
  --memory MIB          Memory in MiB (default 8192)
  --deep-swe-ref REF    Git ref for the deep-swe corpus (default main)
  --keep-runtime        Do not delete the build runtime after checkpointing
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --runtime) RUNTIME=$2; shift 2 ;;
    --checkpoint) CHECKPOINT=$2; shift 2 ;;
    --harness) HARNESS=$2; shift 2 ;;
    --repo) REPO=$2; shift 2 ;;
    --commit) COMMIT=$2; shift 2 ;;
    --model) MODEL=$2; shift 2 ;;
    --secret-name) SECRET_NAME=$2; shift 2 ;;
    --install-script) INSTALL_SCRIPT=$2; shift 2 ;;
    --prepull-tasks) PREPULL_TASKS=$2; shift 2 ;;
    --cpus) CPUS=$2; shift 2 ;;
    --memory) MEMORY=$2; shift 2 ;;
    --deep-swe-ref) DEEP_SWE_REF=$2; shift 2 ;;
    --keep-runtime) KEEP_RUNTIME=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

for required in RUNTIME CHECKPOINT HARNESS REPO COMMIT MODEL; do
  if [ -z "${!required}" ]; then
    echo "missing --$(echo "$required" | tr 'A-Z_' 'a-z-')" >&2
    usage >&2
    exit 2
  fi
done

: "${RUNTA_TOKEN:?RUNTA_TOKEN is not set}"
command -v runta >/dev/null || { echo "runta CLI not found" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq not found" >&2; exit 1; }

step() { printf '\n=== %s\n' "$1" >&2; }
rexec() { runta exec "$RUNTIME" -- sh -lc "$1"; }

step "1/8 creating clean runtime $RUNTIME (${CPUS} vCPU, ${MEMORY} MiB)"
runta run --name "$RUNTIME" --cpus "$CPUS" --memory "$MEMORY"

if [ -n "$SECRET_NAME" ]; then
  step "2/8 storing $SECRET_NAME as a Runta secret stub"
  if [ -z "${!SECRET_NAME:-}" ]; then
    echo "environment variable $SECRET_NAME is empty; export the provider key first" >&2
    exit 1
  fi
  runta secret set "$SECRET_NAME" --value-env "$SECRET_NAME"
  # The real value stays in the egress proxy; the runtime only ever sees the stub.
  rexec "test \"\$$SECRET_NAME\" = runta-secret-stub" \
    || echo "warning: $SECRET_NAME is not exposed as a stub inside the runtime" >&2
else
  step "2/8 skipping secret setup (no --secret-name)"
fi

step "3/8 installing base tooling"
rexec 'set -eu
  export DEBIAN_FRONTEND=noninteractive
  if command -v apt-get >/dev/null; then
    apt-get update -qq
    apt-get install -y -qq git curl ca-certificates jq python3 python3-venv >/dev/null
  fi
  command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
  mkdir -p /work/jobs /work/evidence'

step "4/8 cloning $REPO at $COMMIT"
rexec "set -eu
  export PATH=\"\$HOME/.local/bin:\$PATH\"
  rm -rf /work/harness
  git clone --quiet '$REPO' /work/harness
  cd /work/harness
  git checkout --quiet '$COMMIT'
  git rev-parse HEAD"

step "5/8 installing Harbor, Pier, and the deep-swe corpus"
rexec "set -eu
  export PATH=\"\$HOME/.local/bin:\$PATH\"
  uv tool install --quiet 'harbor[modal]' || uv tool install --quiet harbor
  uv tool install --quiet git+https://github.com/datacurve-ai/pier
  uv tool install --quiet --with 'runta-sdk[harbor]' harbor || true
  rm -rf /work/deep-swe
  git clone --quiet https://github.com/datacurve-ai/deep-swe /work/deep-swe
  cd /work/deep-swe && git checkout --quiet '$DEEP_SWE_REF'
  harbor --version && pier --version"

if [ -n "$INSTALL_SCRIPT" ]; then
  step "6/8 running harness install script"
  [ -f "$INSTALL_SCRIPT" ] || { echo "install script not found: $INSTALL_SCRIPT" >&2; exit 1; }
  runta cp "$INSTALL_SCRIPT" "$RUNTIME:/work/install-harness.sh"
  rexec 'set -eu
    export PATH="$HOME/.local/bin:$PATH"
    chmod +x /work/install-harness.sh
    cd /work/harness && /work/install-harness.sh'
else
  step "6/8 skipping harness install (no --install-script)"
fi

step "7/8 warming caches"
# Pre-pull the images the formal tasks need. Pulling an image is environment prep;
# executing a formal task before the checkpoint would be warm-cache bias.
if [ -n "$PREPULL_TASKS" ] && [ -d "$PREPULL_TASKS" ]; then
  images=$(grep -h '^docker_image' "$PREPULL_TASKS"/*/task.toml 2>/dev/null \
    | sed 's/.*= *"//; s/"$//' | sort -u | tr '\n' ' ')
  if [ -n "$images" ]; then
    echo "pre-pulling $(echo "$images" | wc -w | tr -d ' ') task images" >&2
    rexec "set -eu
      for image in $images; do docker pull -q \"\$image\" || echo \"pull failed: \$image\" >&2; done"
  fi
fi
# The only task executed before the checkpoint is a throwaway sample, never a formal one.
rexec 'set -eu
  export PATH="$HOME/.local/bin:$PATH"
  harbor run -d terminal-bench-sample@2.0 -a oracle -l 1 --jobs-dir /work/warmup \
    >/work/evidence/warmup.log 2>&1 || echo "warmup run failed; see /work/evidence/warmup.log" >&2
  rm -rf /work/warmup'

step "8/8 writing manifest and creating golden checkpoint $CHECKPOINT"
rexec "set -eu
  export PATH=\"\$HOME/.local/bin:\$PATH\"
  cd /work/harness
  cat > /work/manifest.json <<MANIFEST
{
  \"harness\": \"$HARNESS\",
  \"harness_repo\": \"$REPO\",
  \"harness_commit\": \"\$(git rev-parse HEAD)\",
  \"harness_describe\": \"\$(git describe --tags --always 2>/dev/null || echo unknown)\",
  \"model\": \"$MODEL\",
  \"checkpoint\": \"$CHECKPOINT\",
  \"cpus\": $CPUS,
  \"memory_mib\": $MEMORY,
  \"deep_swe_commit\": \"\$(git -C /work/deep-swe rev-parse HEAD)\",
  \"harbor_version\": \"\$(harbor --version 2>&1 | head -1)\",
  \"pier_version\": \"\$(pier --version 2>&1 | head -1)\",
  \"python_version\": \"\$(python3 --version 2>&1)\",
  \"created_at\": \"\$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
}
MANIFEST
  jq . /work/manifest.json"

runta cp "$RUNTIME:/work/manifest.json" "./manifest-${CHECKPOINT}.json"
runta checkpoint create "$RUNTIME" "$CHECKPOINT"

if [ "$KEEP_RUNTIME" -eq 0 ]; then
  runta rm "$RUNTIME"
fi

cat >&2 <<EOF

Golden checkpoint ready: $CHECKPOINT
Manifest saved to:       ./manifest-${CHECKPOINT}.json

Next:
  scripts/run-trials.sh --checkpoint $CHECKPOINT --harness $HARNESS \\
    --model $MODEL --run-id \$(date +%Y-%m-%d)-$HARNESS --tasks tasks.txt --out runs
EOF
