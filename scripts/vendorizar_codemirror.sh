#!/bin/bash
# Regenera web/vendor/codemirror.js a partir das versões fixas em scripts/codemirror/. Roda uma vez, à mão,
# só para trocar de versão: o app não tem build, e o arquivo gerado é o que vai para o repositório.
# Precisa de Node e rede. Instala numa pasta temporária, sem rodar scripts de instalação dos pacotes.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/scripts/codemirror"
VENDOR="$ROOT/vulcan_celox/web/vendor"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/vulcan-codemirror.XXXXXX")"
trap 'find "$WORK" -depth -delete 2>/dev/null || true' EXIT

cp "$SRC/package.json" "$SRC/package-lock.json" "$SRC/entrada.js" "$SRC/gera.mjs" "$WORK/"
(cd "$WORK" && npm ci --ignore-scripts --no-audit --no-fund --silent)
(cd "$WORK" && node gera.mjs "$WORK" "$VENDOR")
