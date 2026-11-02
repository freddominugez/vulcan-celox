#!/bin/bash
# Capturas do manual (vt-26): telas do app com as fixtures e o Lerd simulado, nunca com dado real.
# Gera vulcan_terminal/web/img/manual/*.png a partir do bundle em dist/ (rode scripts/build_app.sh antes).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="${1:-$ROOT/vulcan_terminal/web/img/manual}"
APP="dist/Vulcan Terminal.app/Contents/MacOS/vulcan-terminal"
[ -x "$APP" ] || { echo "rode scripts/build_app.sh antes"; exit 1; }
mkdir -p "$OUT"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/vulcan-shots.XXXXXX")"
cleanup() { [ -n "${API_PID:-}" ] && kill "$API_PID" 2>/dev/null || true; find "$TMP" -depth -delete 2>/dev/null || true; }
trap cleanup EXIT
python3 -I tests/tools/fake_lerd_api.py --site-path loja=/Users/dev/projeto \
  --site-path vulcan-demo="$ROOT/tests/fixtures/harness/repo" --dumps-at 2026-10-31T01:10 > "$TMP/port" 2>/dev/null &
API_PID=$!
for _ in $(seq 1 20); do [ -s "$TMP/port" ] && break; sleep 0.3; done
N=0
shot() {  # shot <nome> <rota> [js extra]
  N=$((N + 1))
  env VULCAN_TERMINAL_HOME="$TMP/home-$N" VULCAN_LEGACY_HOME="$TMP/legacy" VULCAN_VALET_HOME="$TMP/valet" \
    VULCAN_VALET_BIN="$TMP/sem-valet" VULCAN_LERD_BIN="$ROOT/tests/tools/fake-lerd" VULCAN_LERD_DATA="$TMP/lerd-data" \
    VULCAN_LERD_API="http://127.0.0.1:$(cat "$TMP/port")" VULCAN_KEYSTORE=memory VULCAN_AUTOSTART=0 \
    CLAUDE_CONFIG_DIR="$ROOT/tests/fixtures/agents/claude" CODEX_HOME="$ROOT/tests/fixtures/agents/codex" \
    "$APP" --snapshot "$TMP/$1.png" --route "$2" --wait 5 --eval "${3:-}" > /dev/null
  sips -Z 1600 "$TMP/$1.png" --out "$OUT/$1.png" > /dev/null
  echo "$OUT/$1.png"
}
# projeto Node da fixture registrado pela API da própria página, para aparecer na Visão geral e na tela dele
NODE="import('./js/api.mjs').then(function (m) { return m.post('/api/node-projects', { path: '$ROOT/tests/fixtures/node/painel', name: 'painel' }); })
  .then(function () { window.dispatchEvent(new CustomEvent('vulcan-node-changed')); location.hash = '#/__ROTA__'; window.dispatchEvent(new HashChangeEvent('hashchange')); });"
shot visao-geral "#/inicio" "${NODE//__ROTA__/overview}"
shot node-projeto "#/node" "${NODE//__ROTA__/node\/painel}"
shot lerd "#/lerd"
shot agentes "#/agentes"
shot uso-e-custo "#/agentes/uso/2026-10-31"
shot harness "#/sites/vulcan-demo/harness"
# vt-27: compositor aberto no prompt de segurança, com os campos preenchidos pela sessão das fixtures
shot prompts "#/prompts" "setTimeout(function () { window.dispatchEvent(new CustomEvent('vulcan-current-changed')); }, 2500);
  setTimeout(function () { var c = document.querySelector('[data-pick=seguranca]'); if (c) c.click(); }, 4000);"
