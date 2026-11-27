#!/bin/sh
# Builds an offline install bundle for PenguinAgent: Node.js and @prismshadow/penguin-cli
# installed into one tree and packed as a .tar.gz. With --ak install_bundle=<file> the adapter
# copies the bundle into each task container and unpacks it at /opt/penguin-bench, instead
# of installing packages and downloading Node.js and the CLI there. Use it when task
# containers cannot reach the Debian/Ubuntu mirrors, nodejs.org or the npm registry
# reliably; it also saves about two minutes per trial.
#
#   agents/make_install_bundle.sh <out.tar.gz> [penguin_version (0.2.13)] [node_version (24.18.0)]
#
# Run it on a host with the same architecture as the containers (linux x64 or arm64), with
# curl, tar, xz, gzip and sha256sum; it needs nodejs.org and the npm registry once.
set -eu

OUT="$1"
PENGUIN_VERSION="${2:-0.2.13}"
NODE_VERSION="${3:-24.18.0}"
HERE="$(cd "$(dirname "$0")" && pwd)"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE" "$OUT.partial"' EXIT
ROOT="$STAGE/penguin-bench"
mkdir -p "$ROOT/bin"

sh "$HERE/penguin_agent/node_install.sh" "$NODE_VERSION" "$ROOT/node"
PATH="$ROOT/node/bin:$PATH" npm install --global --prefix "$ROOT/npm" --ignore-scripts --no-audit \
  --no-fund --no-update-notifier --loglevel=error --cache "$STAGE/npm-cache" \
  "@prismshadow/penguin-cli@$PENGUIN_VERSION"
rm -rf "$STAGE/npm-cache"

# The same shim the network install writes (absolute paths: the bundle unpacks at /opt).
cat > "$ROOT/bin/penguin" <<'SHIM'
#!/bin/sh
exec /opt/penguin-bench/node/bin/node /opt/penguin-bench/npm/lib/node_modules/@prismshadow/penguin-cli/dist/penguin.js "$@"
SHIM
chmod 755 "$ROOT/bin/penguin"

INSTALLED="$("$ROOT/node/bin/node" -p "require('$ROOT/npm/lib/node_modules/@prismshadow/penguin-cli/package.json').version")"
[ "$INSTALLED" = "$PENGUIN_VERSION" ] || { echo "installed $INSTALLED, expected $PENGUIN_VERSION" >&2; exit 1; }
printf '{"penguin_version": "%s", "node_version": "%s", "arch": "%s", "built_at": "%s"}\n' \
  "$PENGUIN_VERSION" "$NODE_VERSION" "$(uname -m)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$ROOT/bundle.json"

mkdir -p "$(dirname "$OUT")"
# Written beside the target and renamed into place, so that whoever waits for the file never
# reads a half-written archive.
tar -czf "$OUT.partial" -C "$STAGE" penguin-bench
mv "$OUT.partial" "$OUT"
sha256sum "$OUT"
