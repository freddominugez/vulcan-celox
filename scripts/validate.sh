#!/bin/bash
# Sensor único do Vulcan Terminal. Exit 0 = tudo verde; exit 1 no primeiro erro.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# Mesmo critério do launcher: primeiro Python com Tk >= 8.6 (o Tk 8.5 do sistema não desenha no macOS atual)
pick_python() {
  for c in /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if [ -x "$c" ] && "$c" -c 'import sys, tkinter; sys.exit(0 if tkinter.TkVersion >= 8.6 else 1)' >/dev/null 2>&1; then
      echo "$c"; return
    fi
  done
  echo /usr/bin/python3
}
PY="${PYTHON:-$(pick_python)}"
echo "python: $PY ($("$PY" -c 'import sys, tkinter; print(sys.version.split()[0], "Tk", tkinter.TkVersion)'))"
export PYTHONDONTWRITEBYTECODE=1
export TK_SILENCE_DEPRECATION=1

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/vulcan-validate.XXXXXX")"
cleanup() { find "$TMP_ROOT" -depth -delete 2>/dev/null || true; }
trap cleanup EXIT

RUN_ID=0
isolated_env() {
  # cada execução ganha um diretório de dados próprio
  RUN_ID=$((RUN_ID + 1))
  env VULCAN_TERMINAL_HOME="$TMP_ROOT/home-$RUN_ID" \
      VULCAN_LEGACY_HOME="$TMP_ROOT/legacy" \
      VULCAN_VALET_HOME="$TMP_ROOT/valet" \
      VULCAN_VALET_BIN="$TMP_ROOT/sem-valet" \
      VULCAN_LERD_BIN="$TMP_ROOT/sem-lerd" \
      VULCAN_LERD_DATA="$TMP_ROOT/lerd-data" \
      VULCAN_LERD_API="http://127.0.0.1:1" \
      VULCAN_KEYSTORE=memory \
      VULCAN_AUTOSTART=0 \
      CLAUDE_CONFIG_DIR="$ROOT/tests/fixtures/agents/claude" \
      CODEX_HOME="$ROOT/tests/fixtures/agents/codex" \
      "$@"
}

step() { printf '\n==> %s\n' "$*"; }

step "compileall"
"$PY" -m compileall -q vulcan_terminal tests

step "manual em Markdown igual à Ajuda"
"$PY" scripts/manual_md.py "$TMP_ROOT/MANUAL.md" > /dev/null
cmp -s "$TMP_ROOT/MANUAL.md" docs/pt-BR/user-guide.md || { echo "docs/pt-BR/user-guide.md desatualizado: rode python3 scripts/manual_md.py"; exit 1; }

step "unittest"
"$PY" -m unittest discover -s tests -t .

if [ "$PY" != /usr/bin/python3 ] && [ -x /usr/bin/python3 ]; then
  step "unittest (compatibilidade Python 3.9 do sistema)"
  /usr/bin/python3 -m unittest discover -s tests -t .
fi

if [ -f vulcan_terminal/ui/app.py ]; then
  step "selftest (fonte)"
  isolated_env "$PY" -m vulcan_terminal --selftest

  step "selftest (fonte, backend Lerd simulado e painel fora do ar)"
  printf '#!/bin/sh\necho "lerd version 0.0.0-selftest"\n' > "$TMP_ROOT/fake-lerd"
  chmod +x "$TMP_ROOT/fake-lerd"
  isolated_env VULCAN_LERD_BIN="$TMP_ROOT/fake-lerd" "$PY" -m vulcan_terminal --selftest
fi

if [ -f scripts/build_app.sh ]; then
  step "build do bundle"
  bash scripts/build_app.sh
  plutil -lint "dist/Vulcan Terminal.app/Contents/Info.plist"
  icns="dist/Vulcan Terminal.app/Contents/Resources/AppIcon.icns"
  [ "$(/usr/libexec/PlistBuddy -c "Print :CFBundleIconFile" "dist/Vulcan Terminal.app/Contents/Info.plist")" = "AppIcon" ] || { echo "Info.plist sem CFBundleIconFile"; exit 1; }
  shot_png="dist/Vulcan Terminal.app/Contents/Resources/vulcan_terminal/web/img/manual/visao-geral.png"
  [ -f "$shot_png" ] && [ "$(stat -f %z "$shot_png")" -gt 20000 ] || { echo "captura do guia ausente no pacote: $shot_png"; exit 1; }
  [ "$(sips -g pixelWidth "$icns" 2>/dev/null | awk '/pixelWidth/ {print $2}')" = "1024" ] || { echo "AppIcon.icns ausente ou sem 1024 px"; exit 1; }

  # Painel ou faixa visível com um filho em fluxo normal passando da borda de baixo vira erro
  # (overflow hidden + contêiner que espreme); decoração em posição absoluta não conta
  CLIP_JS="setTimeout(function () { document.querySelectorAll('.panel, .ag-banner').forEach(function (el) {
    if (el.offsetParent === null) return;
    var box = el.getBoundingClientRect();
    var cut = Array.prototype.some.call(el.children, function (c) { var pos = getComputedStyle(c).position;
      return pos !== 'absolute' && pos !== 'fixed' && c.getBoundingClientRect().bottom > box.bottom + 1; });
    if (cut) { var h = el.querySelector('h1, h2, h3');
      window.__vtErrors.push('painel cortado: ' + (h ? h.textContent.trim() : el.className)); } }); }, 1800);"

  step "snapshot do app nativo (servidor embutido + interface web)"
  # as fixtures de agentes (CLAUDE_CONFIG_DIR, CODEX_HOME) entram pelo isolated_env; o snapshot falha com erro de JS
  for route in "#/overview" "#/terminals" "#/tasks" "#/agentes" "#/agentes/11111111-2222-4333-8444-555555555555" "#/agentes/historico" "#/agentes/branches" "#/prompts" "#/ambiente" "#/depuracao"; do
    shot="$TMP_ROOT/snapshot-$(printf '%s' "$route" | tr -c 'a-z0-9' '_').png"
    isolated_env "dist/Vulcan Terminal.app/Contents/MacOS/vulcan-terminal" --snapshot "$shot" --route "$route" --wait 3 \
      --eval "$CLIP_JS"
    [ "$(stat -f %z "$shot")" -gt 20000 ] || { echo "snapshot vazio: $shot"; exit 1; }
  done

  step "telas com Lerd simulado"
  # API falsa com as fixtures reais e um lerd falso; o Lerd de verdade nunca é tocado. A sessão de agente das
  # fixtures roda em /Users/dev/projeto entre 01:04 e 01:46 UTC: o site loja aponta para lá e os eventos caem às 01:10.
  # O site vulcan-demo aponta para a fixture com harness do formato do repositório
  "$PY" -I tests/tools/fake_lerd_api.py --site-path loja=/Users/dev/projeto \
    --site-path vulcan-demo="$ROOT/tests/fixtures/harness/repo" --dumps-at 2026-10-31T01:10 \
    > "$TMP_ROOT/lerd-api.port" 2>/dev/null &
  LERD_API_PID=$!
  for _ in 1 2 3 4 5 6 7 8 9 10; do [ -s "$TMP_ROOT/lerd-api.port" ] && break; sleep 0.3; done
  lerd_env() {
    isolated_env VULCAN_LERD_BIN="$ROOT/tests/tools/fake-lerd" VULCAN_LERD_API="http://127.0.0.1:$(cat "$TMP_ROOT/lerd-api.port")" "$@"
  }
  # cada seletor começa como erro pendente e sai da lista quando aparece; o snapshot falha (3) se algum faltar
  expect() {
    printf '%s' "[$1].forEach(function (s) { var tag = 'ausente: ' + s; window.__vtErrors.push(tag);
      var t = setInterval(function () { if (document.querySelector(s)) { var i = window.__vtErrors.indexOf(tag);
        if (i >= 0) window.__vtErrors.splice(i, 1); clearInterval(t); } }, 150); });"
  }
  # Texto selecionado num dump continua selecionado depois de duas voltas da atualização (2 s cada)
  SEL_JS="(function () { var tag = 'seleção perdida na Depuração'; window.__vtErrors.push(tag);
    var t = setInterval(function () { var d = document.querySelector('.debug-dump'); if (!d) return; clearInterval(t);
      var r = document.createRange(); r.selectNodeContents(d); getSelection().removeAllRanges(); getSelection().addRange(r);
      setTimeout(function () { var s = getSelection(); if (!s.isCollapsed && s.anchorNode && s.anchorNode.isConnected) {
        window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1); } }, 4500); }, 150); })();"
  lerd_ok=0
  for pair in "#/ambiente|'[data-xdebug]', '.env-panel'" \
              "#/inicio|'.in-steps', '.in-shot img', '.in-area:nth-child(6)', '.in-dismiss input[type=checkbox]'" \
              "#/ajuda|'.hp-toc', '.hp-search input', '.hp-faq details:nth-of-type(15)'" \
              "#/lerd|'.nav-item.is-on .nav-dot.dot-ok', '.env-panel', '.env-head [data-service=start]'" \
              "#/depuracao|'.debug-group', '.debug-repeat', '.k-log.log-err'" \
              "#/sites/loja/debug|'.debug-group'" \
              "#/sites/loja/logs|'.logs'" \
              "#/agentes/11111111-2222-4333-8444-555555555555|'[data-action=debug-copy]'" \
              "#/sites/vulcan-demo/harness|'.hs-bar', '.hs-item.is-bloqueado', '.hs-pre'" \
              "#/agentes/uso/2026-10-31|'.us-kpis', '.us-seg.us-claude', '.us-seg.us-codex', '.us-note', '.us-link'" \
              "#/overview|'.nav-group[data-group=organizar] .nav-group-head', '.nav-group[data-group=projetos]'" \
              "#/prompts|'.pr-btn .pr-desc', '.pr-tag', '.pc-field', '.pc-preview mark'"; do
    route="${pair%%|*}"
    shot="$TMP_ROOT/lerd-$(printf '%s' "$route" | tr -c 'a-z0-9' '_').png"
    extra=""; wait_s=4
    if [ "$route" = "#/depuracao" ]; then extra="$SEL_JS"; wait_s=7; fi
    # A captura do guia precisa carregar de verdade
    # Busca por "custo" deixa à vista só seções e perguntas com a palavra
    # O botão ? da tela Uso e custo leva à seção custo da Ajuda
    if [ "$route" = "#/agentes/uso/2026-10-31" ]; then extra="(function () { var tag = 'botão ? não levou a #/ajuda/custo'; window.__vtErrors.push(tag);
      setTimeout(function () { document.getElementById('help-here').click(); setTimeout(function () {
        if (location.hash === '#/ajuda/custo' && document.querySelector('#hp-custo')) window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1); }, 900); }, 3500); })();"; wait_s=6; fi
    if [ "$route" = "#/ajuda" ]; then extra="(function () { var tag = 'busca da Ajuda'; window.__vtErrors.push(tag);
      var t = setInterval(function () { var i = document.querySelector('.hp-search input'); if (!i) return; clearInterval(t);
        i.value = 'custo'; i.dispatchEvent(new Event('input', { bubbles: true }));
        var fold = function (x) { return x.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, ''); };
        var vis = Array.prototype.filter.call(document.querySelectorAll('.hp-faq details, .hp-sec[data-text]'), function (e) { return !e.hidden && e.offsetParent !== null; });
        var bad = vis.filter(function (e) { return fold(e.textContent).indexOf('custo') < 0; });
        if (vis.length >= 2 && !bad.length) window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1);
        else window.__vtErrors.push('busca: ' + vis.length + ' visíveis, ' + bad.length + ' sem a palavra'); }, 200); })();"; fi
    # Nenhum marcador {{nome}} à vista na grade de prompts; o compositor tem campos e a prévia muda ao editar
    if [ "$route" = "#/prompts" ]; then extra="setTimeout(function () { var g = document.querySelectorAll('.pr-grid');
      Array.prototype.forEach.call(g, function (e) { if (e.innerText.indexOf('{{') >= 0) window.__vtErrors.push('marcador {{ à vista na grade'); });
      var tag = 'compositor: prévia não acompanhou o campo'; window.__vtErrors.push(tag);
      var c = document.querySelector('[data-pick=seguranca]'); if (!c) return; c.click();
      var i = document.querySelector('.pc-field input[name=branch]'); if (!i || !document.querySelector('.pc-preview mark')) return;
      i.value = 'teste-do-sensor'; i.dispatchEvent(new Event('input', { bubbles: true }));
      if (document.querySelector('.pc-preview').textContent.indexOf('teste-do-sensor') >= 0) window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1); }, 2500);"; wait_s=5; fi
    # Grupos fixos, nenhum item perdido (17: os 16 de antes e Sites PHP) e o grupo Agentes recolhe e volta
    # O foco do teclado continua no cabeçalho do grupo depois de recolher
    # A paleta (⌘K) abre e lista: era a única parte do antigo app.mjs sem roteiro
    if [ "$route" = "#/overview" ]; then extra="setTimeout(function () {
      var ids = Array.prototype.map.call(document.querySelectorAll('.nav-group'), function (g) { return g.dataset.group; }).join(',');
      if (ids !== 'geral,projetos,ambiente,agentes,organizar,ajuda') window.__vtErrors.push('grupos: ' + ids);
      var n = document.querySelectorAll('#nav .nav-item').length; if (n !== 17) window.__vtErrors.push('itens na barra: ' + n);
      document.querySelector('[data-nav-group=agentes]').click();
      var c = document.querySelectorAll('.nav-group[data-group=agentes] .nav-item').length;
      document.querySelector('[data-nav-group=agentes]').click();
      var o = document.querySelectorAll('.nav-group[data-group=agentes] .nav-item').length;
      if (c !== 0 || o !== 5) window.__vtErrors.push('recolher agentes: ' + c + '/' + o);
      var h = document.querySelector('[data-nav-group=agentes]'); h.focus(); h.click();
      var a = document.activeElement; if (!a || a.dataset.navGroup !== 'agentes') window.__vtErrors.push('foco saiu do grupo ao recolher: ' + (a ? a.tagName : 'nada'));
      document.querySelector('[data-nav-group=agentes]').click();
      var pal = 'paleta não abriu ou não listou'; window.__vtErrors.push(pal);
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true, bubbles: true }));
      var inp = document.getElementById('palette-input'); inp.value = 'ajuda'; inp.dispatchEvent(new Event('input', { bubbles: true }));
      setTimeout(function () { if (document.querySelectorAll('.pal-item').length) window.__vtErrors.splice(window.__vtErrors.indexOf(pal), 1); }, 800); }, 2500);"; fi
    # Enter no último passo do guia seleciona o passo e o foco fica nele
    if [ "$route" = "#/inicio" ]; then extra="setTimeout(function () { var i = document.querySelector('.in-shot img');
      if (!i || !i.naturalWidth) window.__vtErrors.push('captura do guia não carregou');
      var s = document.querySelectorAll('.in-step'); var alvo = s[s.length - 1]; if (!alvo) return;
      var spot = alvo.dataset.spot; alvo.focus(); alvo.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
      var on = document.querySelector('.in-step.is-on'); if (!on || on.dataset.spot !== spot) window.__vtErrors.push('Enter no passo do guia não selecionou');
      else if (document.activeElement !== on) window.__vtErrors.push('foco saiu do passo do guia'); }, 3000);"; fi
    lerd_env "dist/Vulcan Terminal.app/Contents/MacOS/vulcan-terminal" --snapshot "$shot" --route "$route" --wait "$wait_s" \
      --eval "$(expect "${pair#*|}") $CLIP_JS $extra" || { lerd_ok=1; echo "falhou com Lerd simulado: $route"; break; }
  done
  # Projeto Node registrado pela própria API da página (fixture só leitura) e aberto na tela dele
  if [ "$lerd_ok" -eq 0 ]; then
    NODE_JS="import('./js/api.mjs').then(function (m) { return m.post('/api/node-projects', { path: '$ROOT/tests/fixtures/node/painel', name: 'painel' }); })
      .then(function () { window.dispatchEvent(new CustomEvent('vulcan-node-changed')); location.hash = '#/node/painel'; }, function (e) { window.__vtErrors.push('node: ' + e.message); });"
    lerd_env "dist/Vulcan Terminal.app/Contents/MacOS/vulcan-terminal" --snapshot "$TMP_ROOT/lerd-node.png" --route "#/node" --wait 5 \
      --eval "$NODE_JS $(expect "'.np-scripts', '.np-supabase', '.np-vercel', '#node-list .site-item'") $CLIP_JS" \
      || { lerd_ok=1; echo "falhou com Lerd simulado: #/node/painel"; }
  fi
  kill "$LERD_API_PID" 2>/dev/null || true
  wait "$LERD_API_PID" 2>/dev/null || true
  [ "$lerd_ok" -eq 0 ] || exit 1

  step "texto digitado sobrevive à mudança da lista de sites"
  # API falsa com um site que aparece e some a cada 3 s; o campo do compositor de Prompts precisa manter o texto
  "$PY" -I tests/tools/fake_lerd_api.py --site-path loja=/Users/dev/projeto --sites-alternam 3 \
    > "$TMP_ROOT/lerd-alterna.port" 2>/dev/null &
  ALT_PID=$!
  for _ in 1 2 3 4 5 6 7 8 9 10; do [ -s "$TMP_ROOT/lerd-alterna.port" ] && break; sleep 0.3; done
  KEEP_JS="setTimeout(function () { var tag = 'texto do compositor perdido com a lista de sites mudando'; window.__vtErrors.push(tag);
    var c = document.querySelector('[data-pick=seguranca]'); if (!c) return; c.click();
    var i = document.querySelector('.pc-field input[name=branch]'); if (!i) return;
    i.value = 'digitado-pelo-usuario'; i.dispatchEvent(new Event('input', { bubbles: true }));
    setTimeout(function () { var j = document.querySelector('.pc-field input[name=branch]');
      if (j && j.value === 'digitado-pelo-usuario') window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1); }, 12000); }, 2500);"
  alt_ok=0
  isolated_env VULCAN_LERD_BIN="$ROOT/tests/tools/fake-lerd" VULCAN_LERD_API="http://127.0.0.1:$(cat "$TMP_ROOT/lerd-alterna.port")" \
    "dist/Vulcan Terminal.app/Contents/MacOS/vulcan-terminal" --snapshot "$TMP_ROOT/lerd-alterna.png" --route "#/prompts" \
    --wait 16 --eval "$KEEP_JS" || alt_ok=1
  kill "$ALT_PID" 2>/dev/null || true
  wait "$ALT_PID" 2>/dev/null || true
  [ "$alt_ok" -eq 0 ] || { echo "falhou: #/prompts com a lista de sites mudando"; exit 1; }

  step "janela presa à origem do app"
  # outra origem que responde de verdade: sem a política de navegação a janela iria para lá e o snapshot sai com 4
  mkdir -p "$TMP_ROOT/fora" && echo '<html><body>fora</body></html>' > "$TMP_ROOT/fora/index.html"
  "$PY" -c 'import http.server, functools, sys
h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=sys.argv[1])
s = http.server.HTTPServer(("127.0.0.1", 0), h); print(s.server_port, flush=True); s.serve_forever()' \
    "$TMP_ROOT/fora" > "$TMP_ROOT/fora.port" 2>/dev/null &
  FORA_PID=$!
  for _ in 1 2 3 4 5 6 7 8 9 10; do [ -s "$TMP_ROOT/fora.port" ] && break; sleep 0.3; done
  fora="http://127.0.0.1:$(cat "$TMP_ROOT/fora.port")/"
  nav_ok=0
  isolated_env "dist/Vulcan Terminal.app/Contents/MacOS/vulcan-terminal" --snapshot "$TMP_ROOT/snapshot-fora.png" \
    --route "#/overview" --wait 3 --eval "location.href = '$fora'" || nav_ok=$?
  kill "$FORA_PID" 2>/dev/null || true
  wait "$FORA_PID" 2>/dev/null || true
  [ "$nav_ok" -eq 0 ] || { echo "a janela saiu do app ou falhou (saída $nav_ok)"; exit 1; }

  step "servidor não importa módulo da pasta atual"
  mkdir -p "$TMP_ROOT/hostil"
  printf "open(%s, 'w').write('x')\n" "'$TMP_ROOT/importou'" > "$TMP_ROOT/hostil/secrets.py"
  app_bin="$ROOT/dist/Vulcan Terminal.app/Contents/MacOS/vulcan-terminal"
  (cd "$TMP_ROOT/hostil" && isolated_env "$app_bin" --snapshot "$TMP_ROOT/snapshot-hostil.png" --wait 2)
  [ ! -e "$TMP_ROOT/importou" ] || { echo "o servidor importou secrets.py da pasta atual"; exit 1; }

  if [ -f scripts/install_app.sh ]; then
    step "instalação em diretórios temporários"
    VULCAN_INSTALL_DEST="$TMP_ROOT/Applications" VULCAN_DESKTOP="$TMP_ROOT/Desktop" \
      bash scripts/install_app.sh
    target="$(readlink "$TMP_ROOT/Desktop/Vulcan Terminal")"
    [ "$target" = "$TMP_ROOT/Applications/Vulcan Terminal.app" ] || { echo "atalho aponta para $target"; exit 1; }
    isolated_env "$TMP_ROOT/Desktop/Vulcan Terminal/Contents/MacOS/vulcan-terminal" --snapshot "$TMP_ROOT/snapshot-atalho.png" --wait 2
    [ "$(stat -f %z "$TMP_ROOT/snapshot-atalho.png")" -gt 20000 ] || { echo "snapshot pelo atalho falhou"; exit 1; }
  fi
fi

printf '\nVALIDATE OK\n'
