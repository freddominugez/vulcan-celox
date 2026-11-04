#!/bin/bash
# Regenerates web/vendor/codemirror.js from the versions pinned in scripts/codemirror/. Runs once, by hand,
# only to change version: the app has no build, and the generated file is what goes into the repository.
# Needs Node and network. Installs into a temporary folder, without running the packages' install scripts.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/scripts/codemirror"
VENDOR="$ROOT/vulcan_celox/web/vendor"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/vulcan-codemirror.XXXXXX")"
trap 'find "$WORK" -depth -delete 2>/dev/null || true' EXIT

cp "$SRC/package.json" "$SRC/package-lock.json" "$SRC/entrada.js" "$SRC/gera.mjs" "$WORK/"
(cd "$WORK" && npm ci --ignore-scripts --no-audit --no-fund --silent)
(cd "$WORK" && node gera.mjs "$WORK" "$VENDOR")
