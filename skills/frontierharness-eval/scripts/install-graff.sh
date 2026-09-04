#!/usr/bin/env bash
# Install a pinned graff Linux binary into the golden checkpoint.
# Runs inside the Runta build runtime as /work/install-harness.sh, cwd /work/harness.
set -euo pipefail

GRAFF_VERSION="${GRAFF_VERSION:-0.0.286}"
GRAFF_COMMIT="${GRAFF_COMMIT:-68540a541e13dac127c7bb4523f77f736601b186}"
INSTALL_DIR=/work/graff

case "$(uname -m)" in
  x86_64|amd64)
    ARCHIVE="graff-x86_64-linux.tar.gz"
    SHA256="2098a13099ee9a645a5a535d04fe5fd8f2602181a93542a3e4b1498ba28474d8"
    ;;
  aarch64|arm64)
    ARCHIVE="graff-aarch64-linux.tar.gz"
    SHA256="bdfd1c1cbb365b729c6e2b1d6c6020085c6344f70fb9e1651bb3a84d1f1df4c0"
    ;;
  *)
    echo "unsupported architecture: $(uname -m)" >&2
    exit 1
    ;;
esac

URL="https://github.com/justrach/codegraff/releases/download/v${GRAFF_VERSION}/${ARCHIVE}"
mkdir -p "$INSTALL_DIR"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

echo "downloading $URL"
curl -fsSL "$URL" -o "$tmp/$ARCHIVE"
actual=$(sha256sum "$tmp/$ARCHIVE" | awk '{print $1}')
if [ "$actual" != "$SHA256" ]; then
  echo "graff tarball digest mismatch: expected $SHA256 got $actual" >&2
  exit 1
fi

tar -xzf "$tmp/$ARCHIVE" -C "$tmp"
bin=$(find "$tmp" -type f -name graff | head -n 1)
if [ -z "$bin" ]; then
  echo "graff binary not found inside $ARCHIVE" >&2
  find "$tmp" -maxdepth 3 -type f >&2
  exit 1
fi

install -m 0755 "$bin" "$INSTALL_DIR/graff"
mkdir -p "$HOME/.local/bin"
ln -sfn "$INSTALL_DIR/graff" "$HOME/.local/bin/graff"
export PATH="$HOME/.local/bin:$PATH"

version_out=$("$INSTALL_DIR/graff" --version 2>&1 || true)
echo "$version_out"
case "$version_out" in
  *"$GRAFF_VERSION"*) ;;
  *)
    echo "warning: graff --version did not contain $GRAFF_VERSION" >&2
    ;;
esac

printf '%s\n' "$GRAFF_VERSION" > "$INSTALL_DIR/VERSION"
printf '%s\n' "$GRAFF_COMMIT" > "$INSTALL_DIR/COMMIT"
printf '%s\n' "$SHA256" > "$INSTALL_DIR/SHA256"
printf '%s\n' "$ARCHIVE" > "$INSTALL_DIR/ARCHIVE"

# Provisioner writes /work/manifest.json after this script; drop extra pins
# where it will merge them if present.
jq -n --arg v "$GRAFF_VERSION" --arg c "$GRAFF_COMMIT" --arg s "$SHA256" \
   --arg a "$ARCHIVE" \
   '{graff_version:$v, graff_commit:$c, graff_sha256:$s, graff_archive:$a}' \
   > /work/harness-extra.json

echo "graff $GRAFF_VERSION installed at $INSTALL_DIR/graff"
