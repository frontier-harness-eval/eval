#!/usr/bin/env bash
# Runs inside the pinned builder. stdout is the archive, stderr is the build log.
set -euo pipefail
cd /tmp
cp /recipe/{package.json,pnpm-lock.yaml} .
npm install -g pnpm@10.34.9 --no-audit --no-fund >&2
pnpm install --frozen-lockfile >&2
cp /usr/local/bin/node .
./node node_modules/@deepseek-ai/dsh/lib/bin.js --version >&2
tar czf - node node_modules
