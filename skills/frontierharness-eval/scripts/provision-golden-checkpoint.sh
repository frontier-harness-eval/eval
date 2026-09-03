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
HARNESS_VERSION=""
REPO=""
COMMIT=""
MODEL=""
SECRET_NAME=""
INSTALL_SCRIPT=""
PREPULL_TASKS=""
COPY_TASKS=""
HARBOR_VERSION=""
HARBOR_ONLY=0
CPUS=4
MEMORY=8192
DEEP_SWE_REF="main"
KEEP_RUNTIME=0
TERMINAL_BENCH_DATASET="terminal-bench/terminal-bench-2-1@sha256:7d7bdc1cbedad549fc1140404bd4dc45e5fd0ea7c4186773687d177ad3a0699a"
NODE_VERSION="22.23.2"
NODE_LINUX_X64_SHA256="b294a556e639d64338823920e5866c21c02741742d2e1529ee1a225c1ec9252a"
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
MCODE_AGENT_SOURCE="$SCRIPT_DIR/../agents/frontierharness_mcode.py"

usage() {
  cat <<EOF
Usage: provision-golden-checkpoint.sh --runtime NAME --checkpoint NAME --harness NAME
                                      [--repo URL --commit SHA] [options]

Required:
  --runtime NAME        Name for the build runtime (deleted unless --keep-runtime)
  --checkpoint NAME     Name for the golden checkpoint
  --harness NAME        Harness identifier used in reports, e.g. my-harness

Options:
  --harness-version VER Version of a packaged or runner-built-in harness
  --repo URL            GitHub repo of the harness under evaluation. Must be paired
                        with --commit; optional for a runner-built-in harness.
  --commit SHA          Commit to pin the harness to. Must be paired with --repo.
  --harbor-version VER  Pin Harbor instead of installing its latest release
  --harbor-only         Skip Pier when every task uses Harbor (the DeepSWE task assets
                        are still cloned for datacurve/* tasks)
  --provider NAME       Kimi K3 provider (default fireworks, as used by the published
                        baselines). One of: $PROVIDER_LIST
                        Each preset picks the model route and key name for you.
  --model ID            Override the model route. Must still be Kimi K3; the benchmark
                        does not vary the model. Required with --provider custom.
  --secret-name NAME    Env var holding the provider key, stored as a Runta secret stub.
                        Defaults to the provider preset, required with custom.
  --install-script PATH Local script uploaded and run inside /work/harness (or /work
                        for a runner-built-in harness) to build it
  --prepull-tasks DIR   Directory of <task>/task.toml files whose images are pre-pulled
  --copy-tasks DIR      Copy public task definitions to /work/frontierharness-tasks;
                        overlay pinned Terminal-Bench and DeepSWE task assets
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
    --harness-version) HARNESS_VERSION=$2; shift 2 ;;
    --repo) REPO=$2; shift 2 ;;
    --commit) COMMIT=$2; shift 2 ;;
    --harbor-version) HARBOR_VERSION=$2; shift 2 ;;
    --harbor-only) HARBOR_ONLY=1; shift ;;
    --provider) PROVIDER=$2; shift 2 ;;
    --model) MODEL=$2; shift 2 ;;
    --secret-name) SECRET_NAME=$2; shift 2 ;;
    --install-script) INSTALL_SCRIPT=$2; shift 2 ;;
    --prepull-tasks) PREPULL_TASKS=$2; shift 2 ;;
    --copy-tasks) COPY_TASKS=$2; shift 2 ;;
    --cpus) CPUS=$2; shift 2 ;;
    --memory) MEMORY=$2; shift 2 ;;
    --deep-swe-ref) DEEP_SWE_REF=$2; shift 2 ;;
    --keep-runtime) KEEP_RUNTIME=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

for required in RUNTIME CHECKPOINT HARNESS; do
  if [ -z "${!required}" ]; then
    echo "missing --$(echo "$required" | tr 'A-Z_' 'a-z-')" >&2
    usage >&2
    exit 2
  fi
done

if { [ -n "$REPO" ] && [ -z "$COMMIT" ]; } || { [ -z "$REPO" ] && [ -n "$COMMIT" ]; }; then
  echo "--repo and --commit must be supplied together" >&2
  usage >&2
  exit 2
fi

if [ -z "$REPO" ] && [ -z "$HARNESS_VERSION" ]; then
  echo "runner-built-in harnesses require --harness-version" >&2
  usage >&2
  exit 2
fi

for version in "$HARNESS_VERSION" "$HARBOR_VERSION"; do
  case "$version" in
    *[!A-Za-z0-9._+-]*) echo "version values may contain only letters, digits, '.', '_', '+', and '-'" >&2; exit 2 ;;
  esac
done

case "$DEEP_SWE_REF" in
  ""|*[!A-Za-z0-9._/+:-]*) echo "invalid --deep-swe-ref: $DEEP_SWE_REF" >&2; exit 2 ;;
esac
if [ -n "$COMMIT" ]; then
  case "$COMMIT" in
    *[!A-Fa-f0-9]*) echo "--commit must be a hexadecimal commit SHA" >&2; exit 2 ;;
  esac
fi
if [ -n "$REPO" ]; then
  case "$REPO" in
    *[!A-Za-z0-9._:/@+-]*) echo "invalid --repo: $REPO" >&2; exit 2 ;;
  esac
fi
for value in "$RUNTIME" "$CHECKPOINT" "$HARNESS"; do
  case "$value" in
    *[!A-Za-z0-9._-]*) echo "runtime, checkpoint, and harness names must be path-safe" >&2; exit 2 ;;
  esac
done

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
case "$MODEL" in
  *[!A-Za-z0-9._:/@+-]*) echo "invalid --model: $MODEL" >&2; exit 2 ;;
esac
case "$SECRET_NAME" in
  ""|[0-9]*|*[!A-Za-z0-9_]*) echo "invalid --secret-name: $SECRET_NAME" >&2; exit 2 ;;
esac

: "${RUNTA_TOKEN:?RUNTA_TOKEN is not set}"
command -v runta >/dev/null || { echo "runta CLI not found" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq not found" >&2; exit 1; }
# Checked before anything is created, so a missing key does not leave a runtime behind.
if [ -z "${!SECRET_NAME:-}" ]; then
  echo "environment variable $SECRET_NAME is empty; export your $PROVIDER key first" >&2
  exit 1
fi

step() { printf '\n=== %s\n' "$1" >&2; }
rexec() { runta exec "$RUNTIME" -- sh -lc "$1"; }

step "1/8 creating clean runtime $RUNTIME (${CPUS} vCPU, ${MEMORY} MiB)"
runta run --name "$RUNTIME" --cpus "$CPUS" --memory "$MEMORY"

step "2/8 storing $SECRET_NAME as a Runta secret stub ($PROVIDER)"
runta secret set "$SECRET_NAME" --value-env "$SECRET_NAME"
# The real value stays in the egress proxy; the runtime only ever sees the stub.
rexec "test \"\$$SECRET_NAME\" = runta-secret-stub" \
  || echo "warning: $SECRET_NAME is not exposed as a stub inside the runtime" >&2

step "3/8 installing base tooling"
rexec 'set -eu
  export DEBIAN_FRONTEND=noninteractive
  if command -v apt-get >/dev/null; then
    apt-get update -qq
    apt-get install -y -qq git curl ca-certificates jq python3 python3-venv >/dev/null
  fi
  command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
  mkdir -p /work/jobs /work/evidence'

if [ -n "$REPO" ]; then
  step "4/8 cloning $REPO at $COMMIT"
  rexec "set -eu
    export PATH=\"\$HOME/.local/bin:\$PATH\"
    rm -rf /work/harness
    git clone --quiet '$REPO' /work/harness
    cd /work/harness
    git checkout --quiet '$COMMIT'
    git rev-parse HEAD"
else
  step "4/8 using runner-built-in harness $HARNESS${HARNESS_VERSION:+@$HARNESS_VERSION}"
fi

HARBOR_PACKAGE="harbor"
HARBOR_PACKAGE_WITH_MODAL="harbor[modal]"
if [ -n "$HARBOR_VERSION" ]; then
  HARBOR_PACKAGE="harbor==$HARBOR_VERSION"
  HARBOR_PACKAGE_WITH_MODAL="harbor[modal]==$HARBOR_VERSION"
fi
if [ "$HARBOR_ONLY" -eq 1 ]; then
  step "5/8 installing Harbor and the deep-swe corpus"
  rexec "set -eu
    export PATH=\"\$HOME/.local/bin:\$PATH\"
    uv tool install --quiet '$HARBOR_PACKAGE'
    rm -rf /work/deep-swe
    git clone --quiet https://github.com/datacurve-ai/deep-swe /work/deep-swe
    cd /work/deep-swe && git checkout --quiet '$DEEP_SWE_REF'
    harbor --version"
else
  step "5/8 installing Harbor, Pier, and the deep-swe corpus"
  rexec "set -eu
    export PATH=\"\$HOME/.local/bin:\$PATH\"
    uv tool install --quiet '$HARBOR_PACKAGE_WITH_MODAL' || uv tool install --quiet '$HARBOR_PACKAGE'
    uv tool install --quiet git+https://github.com/datacurve-ai/pier
    uv tool install --quiet --with 'runta-sdk[harbor]' '$HARBOR_PACKAGE' || true
    rm -rf /work/deep-swe
    git clone --quiet https://github.com/datacurve-ai/deep-swe /work/deep-swe
    cd /work/deep-swe && git checkout --quiet '$DEEP_SWE_REF'
    harbor --version && pier --version"
fi

if [ "$HARNESS" = mcode ]; then
  [ -f "$MCODE_AGENT_SOURCE" ] || { echo "offline MCode agent not found: $MCODE_AGENT_SOURCE" >&2; exit 1; }
  runta cp "$MCODE_AGENT_SOURCE" "$RUNTIME:/work/frontierharness_mcode.py"
  rexec "set -eu
    test \"\$(uname -m)\" = x86_64 || {
      echo 'the pinned MCode runtime bundle currently supports x86_64 Runta runtimes only' >&2
      exit 1
    }
    archive=/work/node-v$NODE_VERSION-linux-x64.tar.gz
    curl -fsSL 'https://nodejs.org/dist/v$NODE_VERSION/node-v$NODE_VERSION-linux-x64.tar.gz' -o \"\$archive\"
    printf '%s  %s\\n' '$NODE_LINUX_X64_SHA256' \"\$archive\" | sha256sum -c -
    rm -rf /work/mcode-runtime /work/mcode-runtime.tar.gz
    mkdir -p /work/mcode-runtime
    tar -xzf \"\$archive\" -C /work/mcode-runtime --strip-components=1
    PATH=/work/mcode-runtime/bin:\"\$PATH\" npm install --global \
      --prefix /work/mcode-runtime --registry=https://registry.npmjs.org \
      '@minimax-ai/code@$HARNESS_VERSION'
    PATH=/work/mcode-runtime/bin:\"\$PATH\" mcode --version \
      | tee /work/evidence/mcode-version
    grep -F '$HARNESS_VERSION' /work/evidence/mcode-version >/dev/null
    /work/mcode-runtime/bin/node --version > /work/evidence/node-version
    tar -czf /work/mcode-runtime.tar.gz -C /work/mcode-runtime .
    sha256sum /work/mcode-runtime.tar.gz | cut -d' ' -f1 \
      > /work/evidence/mcode-bundle.sha256
    rm -rf /work/mcode-runtime \"\$archive\""
fi

if [ -n "$INSTALL_SCRIPT" ]; then
  step "6/8 running harness install script"
  [ -f "$INSTALL_SCRIPT" ] || { echo "install script not found: $INSTALL_SCRIPT" >&2; exit 1; }
  runta cp "$INSTALL_SCRIPT" "$RUNTIME:/work/install-harness.sh"
  rexec 'set -eu
    export PATH="$HOME/.local/bin:$PATH"
    chmod +x /work/install-harness.sh
    if [ -d /work/harness ]; then cd /work/harness; else cd /work; fi
    /work/install-harness.sh'
else
  step "6/8 skipping harness install (no --install-script)"
fi

step "7/8 warming caches"
# Preserve the exact public task definitions in the checkpoint. The pinned upstream
# sources supply environment and verifier assets omitted from this results-only repo;
# every matching task.toml and instruction.md is overlaid with the checked-in copy.
if [ -n "$COPY_TASKS" ]; then
  [ -d "$COPY_TASKS" ] || { echo "task directory not found: $COPY_TASKS" >&2; exit 1; }
  rexec 'rm -rf /work/frontierharness-tasks'
  runta cp "$COPY_TASKS" "$RUNTIME:/work/frontierharness-tasks"
  rexec "set -eu
    export PATH=\"\$HOME/.local/bin:\$PATH\"
    rm -rf /work/terminal-bench-source /work/terminal-bench
    harbor datasets download '$TERMINAL_BENCH_DATASET' \
      --output-dir /work/terminal-bench-source --export
    terminal_source=/work/terminal-bench-source/terminal-bench-2-1
    test -d \"\$terminal_source\"
    mkdir -p /work/terminal-bench/tasks
    test -n \"\$(find /work/frontierharness-tasks -mindepth 2 -maxdepth 2 -name task.toml -print -quit)\"
    terminal_overlaid=0
    deep_swe_overlaid=0
    for public_task in /work/frontierharness-tasks/*; do
      task_name=\"\$(sed -n 's/^name = \"\\([^\"]*\\)\"/\\1/p' \"\$public_task/task.toml\" | head -1)\"
      slug=\"\${task_name#*/}\"
      case \"\$task_name\" in
        terminal-bench/*)
          source_task=\"\$terminal_source/\$slug\"
          test -d \"\$source_task\" || { echo \"missing Terminal-Bench assets for \$task_name\" >&2; exit 1; }
          destination=/work/terminal-bench/tasks/\"\$slug\"
          cp -a \"\$source_task\" \"\$destination\"
          cp \"\$public_task/task.toml\" \"\$destination/task.toml\"
          cp \"\$public_task/instruction.md\" \"\$destination/instruction.md\"
          terminal_overlaid=\$((terminal_overlaid + 1))
          ;;
        datacurve/*)
          destination=/work/deep-swe/tasks/\"\$slug\"
          test -d \"\$destination\" || { echo \"missing DeepSWE assets for \$task_name\" >&2; exit 1; }
          cp \"\$public_task/task.toml\" \"\$destination/task.toml\"
          cp \"\$public_task/instruction.md\" \"\$destination/instruction.md\"
          deep_swe_overlaid=\$((deep_swe_overlaid + 1))
          ;;
        *) echo \"unsupported public task name: \$task_name\" >&2; exit 1 ;;
      esac
    done
    printf '%s\\n' \"\$terminal_overlaid\" > /work/evidence/terminal-bench-overlay-count
    printf '%s\\n' \"\$deep_swe_overlaid\" > /work/evidence/deep-swe-overlay-count
    rm -rf /work/terminal-bench-source"
fi
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
  if [ -d /work/harness ]; then
    harness_commit=\"\$(git -C /work/harness rev-parse HEAD)\"
    harness_describe=\"\$(git -C /work/harness describe --tags --always 2>/dev/null || echo unknown)\"
  else
    harness_commit=
    harness_describe=
  fi
  if [ -d /work/frontierharness-tasks ]; then
    task_count=\"\$(find /work/frontierharness-tasks -mindepth 2 -maxdepth 2 -name task.toml | wc -l | tr -d ' ')\"
    tasks_sha256=\"\$(find /work/frontierharness-tasks -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)\"
    terminal_bench_overlay_count=\"\$(cat /work/evidence/terminal-bench-overlay-count 2>/dev/null || echo 0)\"
    deep_swe_overlay_count=\"\$(cat /work/evidence/deep-swe-overlay-count 2>/dev/null || echo 0)\"
  else
    task_count=0
    tasks_sha256=
    terminal_bench_overlay_count=0
    deep_swe_overlay_count=0
  fi
  if [ -d /work/terminal-bench/tasks ]; then
    terminal_bench_tasks_sha256=\"\$(find /work/terminal-bench/tasks -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)\"
  else
    terminal_bench_tasks_sha256=
  fi
  if [ -d /work/deep-swe/tasks ]; then
    deep_swe_tasks_sha256=\"\$(find /work/deep-swe/tasks -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)\"
  else
    deep_swe_tasks_sha256=
  fi
  cat > /work/manifest.json <<MANIFEST
{
  \"harness\": \"$HARNESS\",
  \"harness_version\": \"$HARNESS_VERSION\",
  \"harness_repo\": \"$REPO\",
  \"harness_commit\": \"\$harness_commit\",
  \"harness_describe\": \"\$harness_describe\",
  \"model\": \"$MODEL\",
  \"provider\": \"$PROVIDER\",
  \"provider_host\": \"$PROVIDER_HOST\",
  \"checkpoint\": \"$CHECKPOINT\",
  \"cpus\": $CPUS,
  \"memory_mib\": $MEMORY,
  \"task_count\": \$task_count,
  \"tasks_sha256\": \"\$tasks_sha256\",
  \"terminal_bench_dataset\": \"$TERMINAL_BENCH_DATASET\",
  \"terminal_bench_overlay_count\": \$terminal_bench_overlay_count,
  \"terminal_bench_tasks_sha256\": \"\$terminal_bench_tasks_sha256\",
  \"deep_swe_overlay_count\": \$deep_swe_overlay_count,
  \"deep_swe_tasks_sha256\": \"\$deep_swe_tasks_sha256\",
  \"deep_swe_commit\": \"\$(git -C /work/deep-swe rev-parse HEAD 2>/dev/null || true)\",
  \"mcode_bundle_sha256\": \"\$(cat /work/evidence/mcode-bundle.sha256 2>/dev/null || true)\",
  \"mcode_agent_sha256\": \"\$(sha256sum /work/frontierharness_mcode.py 2>/dev/null | cut -d' ' -f1 || true)\",
  \"node_version\": \"\$(cat /work/evidence/node-version 2>/dev/null || true)\",
  \"harbor_version\": \"\$(harbor --version 2>&1 | head -1)\",
  \"pier_version\": \"\$(if command -v pier >/dev/null; then pier --version 2>&1 | head -1; fi)\",
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
Provider:                $PROVIDER ($MODEL)

Next:
  $(dirname "$0")/run-trials.sh --checkpoint $CHECKPOINT --harness $HARNESS \\
    --provider $PROVIDER --run-id \$(date +%Y-%m-%d)-$HARNESS --tasks tasks.txt --out runs
EOF
