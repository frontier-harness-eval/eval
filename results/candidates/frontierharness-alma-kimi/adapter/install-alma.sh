#!/bin/sh
# Builds headless Alma on a clean Linux box (the FrontierHarness golden-checkpoint
# runtime). provision-golden-checkpoint.sh runs this as --install-script with the
# harness checkout as the working directory (/work/harness). Everything the trials
# need afterwards is under /work/harness (code, node_modules, bin/server.mjs),
# /work/alma (node for containers, logs) and /work/alma-data (Alma's data dir with
# the provider + eval settings already applied).
set -eu
HARNESS_DIR=$(pwd)
NODE_VERSION=${NODE_VERSION:-v22.22.3}
PNPM_VERSION=${PNPM_VERSION:-10.14.0}
ALMA_DIR=/work/alma
DATA_DIR=${ALMA_FH_DATA_DIR:-/work/alma-data}
PORT=${ALMA_FH_PORT:-23100}
PROVIDER_ID=${ALMA_FH_PROVIDER_ID:-fireworks}
MODEL_ID=${ALMA_FH_MODEL_ID:-accounts/fireworks/models/kimi-k3}
mkdir -p "$ALMA_DIR/logs" "$DATA_DIR"

step() { printf '\n=== install-alma: %s\n' "$1" >&2; }

step "base packages"
export DEBIAN_FRONTEND=noninteractive
if command -v apt-get >/dev/null; then
  apt-get update -qq
  apt-get install -y -qq build-essential python3 pkg-config ca-certificates curl xz-utils git >/dev/null
fi

step "node $NODE_VERSION"
ARCH=$(uname -m)
case "$ARCH" in
  x86_64) NODE_ARCH=x64 ;;
  aarch64|arm64) NODE_ARCH=arm64 ;;
  *) echo "unsupported arch $ARCH" >&2; exit 1 ;;
esac
if ! command -v node >/dev/null || [ "$(node --version)" != "$NODE_VERSION" ]; then
  curl -fsSL "https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-linux-$NODE_ARCH.tar.xz" -o /tmp/node.tar.xz
  tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1
  rm -f /tmp/node.tar.xz
fi
node --version
# The same binary goes into each task container for Alma's remote-workspace daemon.
cp /usr/local/bin/node "$ALMA_DIR/node-linux-$NODE_ARCH"
chmod +x "$ALMA_DIR/node-linux-$NODE_ARCH"
[ -e "$ALMA_DIR/node-linux-x64" ] || ln -s "node-linux-$NODE_ARCH" "$ALMA_DIR/node-linux-x64"

step "pnpm $PNPM_VERSION"
npm install -g "pnpm@$PNPM_VERSION" >/dev/null
pnpm --version

step "dependencies"
cd "$HARNESS_DIR"
export ELECTRON_SKIP_BINARY_DOWNLOAD=1 PUPPETEER_SKIP_DOWNLOAD=1 PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 CI=1
# node-gyp must build against the node we just unpacked (headers included), never
# download headers or Electron's.
export npm_config_nodedir=/usr/local
# The root postinstall rebuilds native modules for Electron, which headless mode
# does not want, so lifecycle scripts are skipped wholesale. Nothing headless
# needs runs from a dependency's postinstall: esbuild/sqlite-vec ship platform
# packages as optional deps, and the two node-gyp modules are rebuilt below.
# (A blanket `pnpm rebuild` dies with spawn E2BIG on this tree.)
pnpm install --frozen-lockfile --ignore-scripts
node scripts/patch-ai-clone.mjs
npx patch-package >/dev/null 2>&1 || true
npm rebuild better-sqlite3 node-pty
node -e "require('better-sqlite3')(':memory:').prepare('select 1 as ok').get(); require('node-pty'); console.log('native modules ok')"

step "headless bundle"
pnpm build:server
test -s bin/server.mjs

step "eval profile (provider + settings)"
export ALMA_FH_HARNESS_DIR="$HARNESS_DIR" ALMA_FH_DATA_DIR="$DATA_DIR" ALMA_FH_PORT="$PORT" ALMA_FH_LOG_DIR="$ALMA_DIR/logs"
DRIVE="$HARNESS_DIR/eval/frontierharness/alma-drive.mjs"
node "$DRIVE" ensure-server --port "$PORT"
node "$DRIVE" configure --port "$PORT" --provider-id "$PROVIDER_ID" --model-id "$MODEL_ID" --api-key runta-secret-stub
node "$DRIVE" stop-server --port "$PORT"
# The checkpoint must not carry a running server or per-run logs.
rm -f "$ALMA_DIR"/logs/*.pid "$ALMA_DIR"/logs/*.log "$ALMA_DIR"/logs/fw-usage.jsonl

cat > "$ALMA_DIR/alma-manifest.json" <<EOF
{
  "harness": "alma",
  "alma_version": "$(node -p "require('$HARNESS_DIR/package.json').version")",
  "alma_commit": "$(git -C "$HARNESS_DIR" rev-parse HEAD 2>/dev/null || echo unknown)",
  "node_version": "$(node --version)",
  "pnpm_version": "$(pnpm --version)",
  "mode": "headless bin/server.mjs on the runtime host; task container attached as an Alma remote host through eval/ssh-docker-shim.sh (docker exec)",
  "provider_id": "$PROVIDER_ID",
  "model_id": "$MODEL_ID",
  "provider_base_url": "http://127.0.0.1:${ALMA_FH_PROXY_PORT:-8899}/inference/v1 (usage-logging proxy → https://api.fireworks.ai)",
  "settings": {
    "security.autoApproveToolRequests": true,
    "advanced.programmaticToolCalling": false,
    "general.analyticsEnabled": false,
    "lean_profile": ${ALMA_FH_LEAN:-0},
    "other": "Alma shipped defaults"
  },
  "env": {
    "ALMA_TOOL_APPROVAL": "allow",
    "ALMA_NO_OPENAI_CACHE_CONTROL": "1",
    "BENCH_PREFIX": ""
  }
}
EOF
chmod +x "$HARNESS_DIR"/eval/frontierharness/*.sh "$HARNESS_DIR"/eval/ssh-docker-shim.sh
step "done"
cat "$ALMA_DIR/alma-manifest.json"
