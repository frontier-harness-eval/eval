#!/usr/bin/env bash
# Provision a clean Runta runtime, install the FrontierHarness benchmark stack and the
# harness under evaluation, then freeze the result as a golden checkpoint.
set -euo pipefail

# shellcheck source=providers.sh
. "$(cd "$(dirname "$0")" && pwd)/providers.sh"

# FrontierHarness holds the model constant at Kimi K3 so the harness is the only thing
# that varies. The provider is free; the published baselines used Fireworks.
PROVIDER="fireworks"

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
DISK_GIB=100
DEEP_SWE_REF="v1.1"
HARBOR_PIN="harbor[modal]==0.22.0"
HARBOR_PIN_FALLBACK="harbor==0.22.0"
PIER_PIN="datacurve-pier==0.3.1"
KEEP_RUNTIME=0

usage() {
  cat <<EOF
Usage: provision-golden-checkpoint.sh --runtime NAME --checkpoint NAME --harness NAME
                                      --repo URL --commit SHA [options]

Required:
  --runtime NAME        Name for the build runtime (deleted unless --keep-runtime)
  --checkpoint NAME     Name for the golden checkpoint
  --harness NAME        Harness identifier used in reports, e.g. my-harness
  --repo URL            GitHub repo of the harness under evaluation
  --commit SHA          Commit to pin the harness to

Options:
  --provider NAME       Kimi K3 provider (default fireworks, as used by the published
                        baselines). One of: $PROVIDER_LIST
                        Each preset picks the model route and key name for you.
  --model ID            Override the model route. Must still be Kimi K3; the benchmark
                        does not vary the model. Required with --provider custom.
  --secret-name NAME    Env var holding the provider key, stored as a Runta secret stub.
                        Defaults to the provider preset, required with custom.
  --install-script PATH Local script uploaded and run inside /work/harness to build it
  --prepull-tasks DIR   Directory of <task>/task.toml files whose images are pre-pulled
  --cpus N              vCPUs (default 4)
  --memory MIB          Memory in MiB (default 8192)
  --disk-size-gib GIB   Writable overlay capacity (default 100). The eval environment
                        needs this much: a harness built from source plus the pre-pulled
                        task images overflows the 16 GiB Runtime Image default.
  --deep-swe-ref REF    Git ref for the deep-swe corpus (default v1.1, matching benchmark.json)
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
    --provider) PROVIDER=$2; shift 2 ;;
    --model) MODEL=$2; shift 2 ;;
    --secret-name) SECRET_NAME=$2; shift 2 ;;
    --install-script) INSTALL_SCRIPT=$2; shift 2 ;;
    --prepull-tasks) PREPULL_TASKS=$2; shift 2 ;;
    --cpus) CPUS=$2; shift 2 ;;
    --memory) MEMORY=$2; shift 2 ;;
    --disk-size-gib) DISK_GIB=$2; shift 2 ;;
    --deep-swe-ref) DEEP_SWE_REF=$2; shift 2 ;;
    --keep-runtime) KEEP_RUNTIME=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

for required in RUNTIME CHECKPOINT HARNESS REPO COMMIT; do
  if [ -z "${!required}" ]; then
    echo "missing --$(echo "$required" | tr 'A-Z_' 'a-z-')" >&2
    usage >&2
    exit 2
  fi
done

case "$DISK_GIB" in
  ''|*[!0-9]*) echo "--disk-size-gib must be a whole number of GiB" >&2; exit 2 ;;
esac
if [ "$DISK_GIB" -lt 100 ]; then
  echo "warning: disk ${DISK_GIB} GiB is below the 100 GiB the eval environment needs" >&2
fi

if ! resolve_provider "$PROVIDER"; then
  echo "unknown --provider $PROVIDER; expected one of: $PROVIDER_LIST" >&2
  exit 2
fi
# Explicit flags win over the provider preset.
MODEL=${MODEL:-$PROVIDER_MODEL}
SECRET_NAME=${SECRET_NAME:-$PROVIDER_SECRET}

if [ -z "$MODEL" ] || [ -z "$SECRET_NAME" ]; then
  echo "--provider custom needs both --model and --secret-name" >&2
  exit 2
fi
warn_unless_kimi_k3 "$MODEL"

require_runta_auth || exit 1
# Checked before anything is created, so a missing key does not leave a runtime behind.
# A key already on the tenant is enough to proceed: the stub appears in a runtime from
# the secret's existence alone, so re-cutting a checkpoint does not need the plaintext a
# second time. Storing it again is still preferred when the value is at hand, since that
# is the only way to rotate it.
STORE_SECRET=1
if [ -z "${!SECRET_NAME:-}" ]; then
  if runta_secret_exists "$SECRET_NAME"; then
    STORE_SECRET=0
  else
    echo "environment variable $SECRET_NAME is empty and no $SECRET_NAME secret is stored on the tenant; export your $PROVIDER key first" >&2
    exit 1
  fi
fi

step() { printf '\n=== %s\n' "$1" >&2; }
rexec() { runta exec "$RUNTIME" -- sh -lc "$1"; }

step "1/9 creating clean runtime $RUNTIME (${CPUS} vCPU, ${MEMORY} MiB, disk ${DISK_GIB} GiB)"
runta run --name "$RUNTIME" --cpus "$CPUS" --memory "$MEMORY" --disk-size-gib "$DISK_GIB"

if [ "$STORE_SECRET" -eq 1 ]; then
  step "2/9 storing $SECRET_NAME as a Runta secret stub ($PROVIDER)"
  runta secret set "$SECRET_NAME" --value-env "$SECRET_NAME"
else
  step "2/9 reusing the $SECRET_NAME secret already on the tenant ($PROVIDER)"
fi
# The real value stays in the egress proxy; the runtime only ever sees the stub.
rexec "test \"\$$SECRET_NAME\" = runta-secret-stub" \
  || echo "warning: $SECRET_NAME is not exposed as a stub inside the runtime" >&2
if [ -n "$PROVIDER_HOST" ]; then
  apply_provider_egress "$RUNTIME" "$PROVIDER_HOST" || true
fi

step "3/9 installing base tooling"
rexec 'set -eu
  export DEBIAN_FRONTEND=noninteractive
  if command -v apt-get >/dev/null; then
    apt-get update -qq
    apt-get install -y -qq git curl ca-certificates jq python3 python3-venv >/dev/null
  fi
  command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
  mkdir -p /work/jobs /work/evidence'

step "4/9 cloning $REPO at $COMMIT"
rexec "set -eu
  export PATH=\"\$HOME/.local/bin:\$PATH\"
  rm -rf /work/harness
  git clone --quiet '$REPO' /work/harness
  cd /work/harness
  git checkout --quiet '$COMMIT'
  git rev-parse HEAD"

step "5/9 installing Harbor, Pier, and the deep-swe corpus"
rexec "set -eu
  export PATH=\"\$HOME/.local/bin:\$PATH\"
  uv tool install --quiet --with 'runta-sdk[harbor]' '$HARBOR_PIN' \
    || uv tool install --quiet --with 'runta-sdk[harbor]' '$HARBOR_PIN_FALLBACK' \
    || uv tool install --quiet '$HARBOR_PIN_FALLBACK'
  uv tool install --quiet '$PIER_PIN'
  rm -rf /work/deep-swe
  git clone --quiet https://github.com/datacurve-ai/deep-swe /work/deep-swe
  cd /work/deep-swe && git checkout --quiet '$DEEP_SWE_REF'
  harbor --version && pier --version"

if [ -n "$INSTALL_SCRIPT" ]; then
  step "6/9 running harness install script"
  [ -f "$INSTALL_SCRIPT" ] || { echo "install script not found: $INSTALL_SCRIPT" >&2; exit 1; }
  runta cp "$INSTALL_SCRIPT" "$RUNTIME:/work/install-harness.sh"
  rexec 'set -eu
    export PATH="$HOME/.local/bin:$PATH"
    chmod +x /work/install-harness.sh
    cd /work/harness && /work/install-harness.sh'
else
  step "6/9 skipping harness install (no --install-script)"
fi

step "7/9 installing the egress CA overlay"
# Runta terminates TLS on egress. The runtime host trusts the proxy CA but task
# containers do not, so every HTTPS download inside a task fails cert validation. That
# breaks verifiers before they run: terminal-bench test.sh curls uv from astral.sh, gets
# a cert error, and writes reward 0 no matter what the agent did. Handing the container
# the same trust the host already has keeps a failed download from scoring as a failed
# task. Harbor names the task service "main".
rexec 'set -eu
  cat > /work/runta-ca-overlay.yaml <<OVERLAY
services:
  main:
    volumes:
      - /etc/ssl/certs/ca-certificates.crt:/etc/ssl/certs/runta-ca-bundle.crt:ro
      - /usr/local/share/ca-certificates/runta-egress.crt:/usr/local/share/ca-certificates/runta-egress.crt:ro
    environment:
      CURL_CA_BUNDLE: /etc/ssl/certs/runta-ca-bundle.crt
      SSL_CERT_FILE: /etc/ssl/certs/runta-ca-bundle.crt
      REQUESTS_CA_BUNDLE: /etc/ssl/certs/runta-ca-bundle.crt
      PIP_CERT: /etc/ssl/certs/runta-ca-bundle.crt
      GIT_SSL_CAINFO: /etc/ssl/certs/runta-ca-bundle.crt
      NODE_EXTRA_CA_CERTS: /usr/local/share/ca-certificates/runta-egress.crt
      UV_NATIVE_TLS: "1"
OVERLAY'

step "8/9 warming caches"
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
    --extra-docker-compose /work/runta-ca-overlay.yaml -y \
    >/work/evidence/warmup.log 2>&1 || echo "warmup run failed; see /work/evidence/warmup.log" >&2
  rm -rf /work/warmup'

step "9/9 writing manifest and creating golden checkpoint $CHECKPOINT"
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
  \"provider\": \"$PROVIDER\",
  \"provider_host\": \"$PROVIDER_HOST\",
  \"checkpoint\": \"$CHECKPOINT\",
  \"cpus\": $CPUS,
  \"memory_mib\": $MEMORY,
  \"disk_size_gib\": $DISK_GIB,
  \"deep_swe_commit\": \"\$(git -C /work/deep-swe rev-parse HEAD)\",
  \"deep_swe_ref\": \"$DEEP_SWE_REF\",
  \"harbor_pin\": \"$HARBOR_PIN_FALLBACK\",
  \"pier_pin\": \"$PIER_PIN\",
  \"harbor_version\": \"\$(harbor --version 2>&1 | head -1)\",
  \"pier_version\": \"\$(pier --version 2>&1 | head -1)\",
  \"python_version\": \"\$(python3 --version 2>&1)\",
  \"created_at\": \"\$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
}
MANIFEST
  jq . /work/manifest.json"

# runta cp 0.1.21 transfers the file but can still exit non-zero ("unable to create
# download tar archive"), so the copy is judged on what arrived, not on the exit code.
runta cp "$RUNTIME:/work/manifest.json" "./manifest-${CHECKPOINT}.json" || true
jq -e . "./manifest-${CHECKPOINT}.json" >/dev/null \
  || { echo "manifest did not copy out of $RUNTIME" >&2; exit 1; }

runta checkpoint create "$RUNTIME" "$CHECKPOINT"

if [ "$KEEP_RUNTIME" -eq 0 ]; then
  runta rm "$RUNTIME"
fi

cat >&2 <<EOF

Golden checkpoint ready: $CHECKPOINT
Manifest saved to:       ./manifest-${CHECKPOINT}.json
Provider:                $PROVIDER ($MODEL)

Next:
  $(dirname "$0")/run-trials.sh --checkpoint $CHECKPOINT --harness $HARNESS \\
    --provider $PROVIDER --run-id \$(date +%Y-%m-%d)-$HARNESS --out runs
EOF
