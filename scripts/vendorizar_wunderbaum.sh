#!/bin/bash
# Copies the Wunderbaum tree into web/vendor/. Runs by hand, only to change version: the app has no build and
# the copied files are what goes into the repository. Needs network. Installs nothing and runs nothing from the package.
set -euo pipefail

VERSION="0.15.0"
TARBALL_SHA256="bec21f0a188c11db22e53f6b06696ec82304a01aaab8910a8319d256017b99e6"
URL="https://registry.npmjs.org/wunderbaum/-/wunderbaum-$VERSION.tgz"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$ROOT/vulcan_celox/web/vendor"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/vulcan-wunderbaum.XXXXXX")"
trap 'find "$WORK" -depth -delete 2>/dev/null || true' EXIT

curl -fsSL --max-time 120 -o "$WORK/pacote.tgz" "$URL"
got="$(shasum -a 256 "$WORK/pacote.tgz" | cut -d' ' -f1)"
if [ "$got" != "$TARBALL_SHA256" ]; then
  echo "soma SHA-256 diferente: esperava $TARBALL_SHA256, veio $got" >&2
  exit 1
fi
tar -xzf "$WORK/pacote.tgz" -C "$WORK" package/dist/wunderbaum.umd.min.js package/dist/wunderbaum.css package/LICENSE
cp "$WORK/package/dist/wunderbaum.umd.min.js" "$WORK/package/dist/wunderbaum.css" "$VENDOR/"
echo "Wunderbaum $VERSION copiada para $VENDOR"
