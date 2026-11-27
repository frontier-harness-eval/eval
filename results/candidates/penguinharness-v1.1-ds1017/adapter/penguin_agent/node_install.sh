#!/bin/sh
# Installs an official Node.js build into a private prefix (default /opt/penguin-bench/node).
#
#   node_install.sh <version> <prefix> [<dist base url>]
#
# The task image's own PATH and any Node it ships are left untouched: PenguinHarness runs
# from the private prefix, so the agent's shell commands still see the task's toolchain.
# The tarball is verified against the release's SHASUMS256.txt. glibc only: official Node
# builds do not run on musl (Alpine) images.
set -eu

VERSION="$1"
PREFIX="$2"
DIST="${3:-https://nodejs.org/dist}"

if [ -x "$PREFIX/bin/node" ] && [ "$("$PREFIX/bin/node" --version 2>/dev/null)" = "v$VERSION" ]; then
  echo "node v$VERSION already installed at $PREFIX"
  exit 0
fi

case "$(uname -m)" in
  x86_64 | amd64) ARCH=x64 ;;
  aarch64 | arm64) ARCH=arm64 ;;
  *)
    echo "node_install.sh: unsupported architecture $(uname -m)" >&2
    exit 1
    ;;
esac

if ls /lib/ld-musl-* >/dev/null 2>&1; then
  echo "node_install.sh: musl libc (Alpine) is not supported; official Node builds need glibc" >&2
  exit 1
fi

NAME="node-v$VERSION-linux-$ARCH"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

curl -fsSL --retry 5 --retry-delay 3 -o "$TMP/$NAME.tar.xz" "$DIST/v$VERSION/$NAME.tar.xz"
curl -fsSL --retry 5 --retry-delay 3 -o "$TMP/SHASUMS256.txt" "$DIST/v$VERSION/SHASUMS256.txt"
EXPECTED="$(grep " $NAME.tar.xz\$" "$TMP/SHASUMS256.txt" | cut -d' ' -f1)"
ACTUAL="$(sha256sum "$TMP/$NAME.tar.xz" | cut -d' ' -f1)"
if [ -z "$EXPECTED" ] || [ "$EXPECTED" != "$ACTUAL" ]; then
  echo "node_install.sh: checksum mismatch for $NAME.tar.xz" >&2
  exit 1
fi

mkdir -p "$PREFIX"
tar -xJf "$TMP/$NAME.tar.xz" -C "$PREFIX" --strip-components=1 --no-same-owner
"$PREFIX/bin/node" --version
