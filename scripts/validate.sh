#!/bin/bash
# Single sensor for Vulcan Celox. Exit 0 = all green; exit 1 on the first error.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# Same criterion as the launcher: first Python with Tk >= 8.6 (the system Tk 8.5 does not draw on current macOS)
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
# test copies are not registered with macOS: they became repeated icons in Launchpad
LSREGISTER=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
unregister() { [ -x "$LSREGISTER" ] && "$LSREGISTER" -u "$1" >/dev/null 2>&1 || true; }
cleanup() { unregister "$ROOT/dist/Vulcan Celox.app"; unregister "$TMP_ROOT/Applications/Vulcan Celox.app"; find "$TMP_ROOT" -depth -delete 2>/dev/null || true; }
trap cleanup EXIT

RUN_ID=0
isolated_env() {
  # each run gets its own data directory
  RUN_ID=$((RUN_ID + 1))
  env VULCAN_CELOX_HOME="$TMP_ROOT/home-$RUN_ID" \
      VULCAN_LEGACY_HOME="$TMP_ROOT/legacy" \
      VULCAN_VALET_HOME="$TMP_ROOT/valet" \
      VULCAN_VALET_BIN="$TMP_ROOT/sem-valet" \
      VULCAN_LERD_BIN="$TMP_ROOT/sem-lerd" \
      VULCAN_LERD_DATA="$TMP_ROOT/lerd-data" \
      VULCAN_LERD_API="http://127.0.0.1:1" \
      VULCAN_KEYSTORE=memory \
      VULCAN_AUTOSTART=0 VULCAN_UPDATE_CHECK=0 \
      VULCAN_LANGUAGE="${SENSOR_LANGUAGE:-pt}" \
      CLAUDE_CONFIG_DIR="$ROOT/tests/fixtures/agents/claude" \
      CODEX_HOME="$ROOT/tests/fixtures/agents/codex" \
      "$@"
}

step() { printf '\n==> %s\n' "$*"; }

step "compileall"
"$PY" -m compileall -q vulcan_celox tests

step "manual em Markdown igual à Ajuda"
"$PY" scripts/manual_md.py "$TMP_ROOT/MANUAL.md" > /dev/null
cmp -s "$TMP_ROOT/MANUAL.md" docs/pt-BR/user-guide.md || { echo "docs/pt-BR/user-guide.md desatualizado: rode python3 scripts/manual_md.py"; exit 1; }
"$PY" scripts/manual_md.py "$TMP_ROOT/user-guide.md" --en > /dev/null
cmp -s "$TMP_ROOT/user-guide.md" docs/en/user-guide.md || { echo "docs/en/user-guide.md desatualizado: rode python3 scripts/manual_md.py"; exit 1; }

step "unittest"
"$PY" -m unittest discover -s tests -t .

if [ "$PY" != /usr/bin/python3 ] && [ -x /usr/bin/python3 ]; then
  step "unittest (compatibilidade Python 3.9 do sistema)"
  /usr/bin/python3 -m unittest discover -s tests -t .
fi

if [ -f vulcan_celox/ui/app.py ]; then
  step "selftest (fonte)"
  isolated_env "$PY" -m vulcan_celox --selftest

  step "selftest (fonte, backend Lerd simulado e painel fora do ar)"
  printf '#!/bin/sh\necho "lerd version 0.0.0-selftest"\n' > "$TMP_ROOT/fake-lerd"
  chmod +x "$TMP_ROOT/fake-lerd"
  isolated_env VULCAN_LERD_BIN="$TMP_ROOT/fake-lerd" "$PY" -m vulcan_celox --selftest
fi

if [ -f scripts/build_app.sh ]; then
  step "build do bundle"
  bash scripts/build_app.sh
  plutil -lint "dist/Vulcan Celox.app/Contents/Info.plist"
  icns="dist/Vulcan Celox.app/Contents/Resources/AppIcon.icns"
  [ "$(/usr/libexec/PlistBuddy -c "Print :CFBundleIconFile" "dist/Vulcan Celox.app/Contents/Info.plist")" = "AppIcon" ] || { echo "Info.plist sem CFBundleIconFile"; exit 1; }
  shot_png="dist/Vulcan Celox.app/Contents/Resources/vulcan_celox/web/img/manual/visao-geral.png"
  [ -f "$shot_png" ] && [ "$(stat -f %z "$shot_png")" -gt 20000 ] || { echo "captura do guia ausente no pacote: $shot_png"; exit 1; }
  [ "$(sips -g pixelWidth "$icns" 2>/dev/null | awk '/pixelWidth/ {print $2}')" = "1024" ] || { echo "AppIcon.icns ausente ou sem 1024 px"; exit 1; }

  # a visible panel or strip with a normal-flow child extending past the bottom edge becomes an error
  # (overflow hidden + a container that squeezes); absolutely positioned decoration does not count
  CLIP_JS="setTimeout(function () { document.querySelectorAll('.panel, .ag-banner').forEach(function (el) {
    if (el.offsetParent === null) return;
    var box = el.getBoundingClientRect();
    var cut = Array.prototype.some.call(el.children, function (c) { var pos = getComputedStyle(c).position;
      return pos !== 'absolute' && pos !== 'fixed' && c.getBoundingClientRect().bottom > box.bottom + 1; });
    if (cut) { var h = el.querySelector('h1, h2, h3');
      window.__vtErrors.push('painel cortado: ' + (h ? h.textContent.trim() : el.className)); } }); }, 1800);"

  step "snapshot do app nativo (servidor embutido + interface web)"
  # the agent fixtures (CLAUDE_CONFIG_DIR, CODEX_HOME) enter through isolated_env; the snapshot fails on a JS error
  for route in "#/overview" "#/codigo" "#/terminals" "#/tasks" "#/agentes" "#/agentes/11111111-2222-4333-8444-555555555555" "#/agentes/historico" "#/agentes/branches" "#/prompts" "#/ambiente" "#/depuracao"; do
    shot="$TMP_ROOT/snapshot-$(printf '%s' "$route" | tr -c 'a-z0-9' '_').png"
    isolated_env "dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --snapshot "$shot" --route "$route" --wait 3 \
      --eval "$CLIP_JS"
    [ "$(stat -f %z "$shot")" -gt 20000 ] || { echo "snapshot vazio: $shot"; exit 1; }
  done

  . scripts/sensores_interface.sh

  step "telas com Lerd simulado"
  # fake API with the real fixtures and a fake lerd; the real Lerd is never touched. The agent session in the
  # fixtures runs in /Users/dev/projeto between 01:04 and 01:46 UTC: the loja site points there and the events land at 01:10.
  # the vulcan-demo site points to the fixture with a harness in the repository format
  "$PY" -I tests/tools/fake_lerd_api.py --site-path loja=/Users/dev/projeto \
    --site-path vulcan-demo="$ROOT/tests/fixtures/harness/repo" --dumps-at 2026-10-31T01:10 \
    > "$TMP_ROOT/lerd-api.port" 2>"$TMP_ROOT/lerd-api.err" &
  LERD_API_PID=$!
  for _ in 1 2 3 4 5 6 7 8 9 10; do [ -s "$TMP_ROOT/lerd-api.port" ] && break; sleep 0.3; done
  # on a failure, what the simulated API answered and what the app's core concluded from it
  lerd_diag() {
    echo "porta da API simulada: '$(cat "$TMP_ROOT/lerd-api.port")'"; head -c 1500 "$TMP_ROOT/lerd-api.err"
    curl -s -m 3 "http://127.0.0.1:$(cat "$TMP_ROOT/lerd-api.port")/api/status" | head -c 300; echo
    lerd_env "$PY" -m vulcan_celox --doctor 2>&1 | head -c 1200; echo
    tail -n 40 "$(ls -td "$TMP_ROOT"/home-* | head -1)/logs/"*.log 2>/dev/null
  }
  lerd_env() {
    isolated_env VULCAN_LERD_BIN="$ROOT/tests/tools/fake-lerd" VULCAN_LERD_API="http://127.0.0.1:$(cat "$TMP_ROOT/lerd-api.port")" "$@"
  }
  # text selected in a dump stays selected after two refresh cycles (2 s each)
  SEL_JS="(function () { var tag = 'seleção perdida na Depuração'; window.__vtErrors.push(tag);
    var t = setInterval(function () { var d = document.querySelector('.debug-dump'); if (!d) return; clearInterval(t);
      var r = document.createRange(); r.selectNodeContents(d); getSelection().removeAllRanges(); getSelection().addRange(r);
      setTimeout(function () { var s = getSelection(); if (!s.isCollapsed && s.anchorNode && s.anchorNode.isConnected) {
        window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1); } }, 4500); }, 150); })();"
  lerd_ok=0
  for pair in "#/ambiente|'[data-xdebug]', '.env-panel'" \
              "#/inicio|'.in-steps', '.in-area[data-card=depuracao]', '.in-area[data-card=prompts]', '.in-area[data-card=config]', '.in-area.is-static', '.in-dismiss input[type=checkbox]'" \
              "#/ajuda|'.hp-toc', '.hp-search input', '.hp-faq details:nth-of-type(15)'" \
              "#/config|'[data-side=tags]', '[data-theme=escuro]', '[data-lang=pt]', '[data-cf=welcome]', '[data-role=key] .key-form', '[data-cf-action=open-data]', '[data-data=backup]', '[data-data=inspect]', '[data-data=mask]', '[data-cf=update]', '[data-role=update]'" \
              "#/lerd|'.nav-item.is-on .nav-dot.dot-ok', '.env-panel', '.env-head [data-service=start]'" \
              "#/depuracao|'.debug-group', '.debug-repeat', '.k-log.log-err'" \
              "#/sites/loja/debug|'.debug-group'" \
              "#/sites/loja/logs|'.logs'" \
              "#/sites/loja/tasks|'.ws-body'" \
              "#/agentes/11111111-2222-4333-8444-555555555555|'[data-action=debug-copy]'" \
              "#/sites/vulcan-demo/harness|'.hs-bar', '.hs-item.is-bloqueado', '.hs-pre'" \
              "#/agentes/uso/2026-10-31|'.us-kpis', '.us-seg.us-claude', '.us-seg.us-codex', '.us-note', '.us-link'" \
              "#/overview|'.nav-group[data-group=organizar] .nav-group-head', '.nav-group[data-group=projetos]'" \
              "#/prompts|'.pr-btn .pr-desc', '.pr-tag', '.pc-field', '.pc-preview mark'"; do
    route="${pair%%|*}"
    shot="$TMP_ROOT/lerd-$(printf '%s' "$route" | tr -c 'a-z0-9' '_').png"
    extra=""; wait_s=4
    if [ "$route" = "#/depuracao" ]; then extra="$SEL_JS"; wait_s=7; fi
    # the green dot waits for the first status of the simulated Lerd, slower on a clean CI machine
    if [ "$route" = "#/lerd" ]; then wait_s=8; extra="setTimeout(function () { var d = document.querySelector('.nav-item.is-on .nav-dot');
      if (d && !d.classList.contains('dot-ok')) { window.__vtErrors.push('bolinha do Lerd: ' + d.className + ' / ' + d.title);
        import('./js/api.mjs').then(function (m) { return m.get('/api/state'); }).then(function (st) { window.__vtErrors.push('estado: ' + JSON.stringify(st.status) + ' ' + JSON.stringify(st.backend)); }); } }, 6500);"; fi
    # light theme: the tabs of a site follow the page, and the title of a task can be read
    if [ "$route" = "#/sites/loja/tasks" ]; then extra="$(cat tests/tools/sensor_abas_tema_claro.js)"; wait_s=6; fi
    # the guide screenshot must really load
    # searching for "custo" leaves only sections and questions with that word in view
    # the ? button on the Uso e custo screen leads to the custo section of Help
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
    # no {{nome}} placeholder in view in the prompt grid; the composer has fields and the preview changes on edit
    if [ "$route" = "#/prompts" ]; then extra="setTimeout(function () { var g = document.querySelectorAll('.pr-grid');
      Array.prototype.forEach.call(g, function (e) { if (e.innerText.indexOf('{{') >= 0) window.__vtErrors.push('marcador {{ à vista na grade'); });
      var tag = 'compositor: prévia não acompanhou o campo'; window.__vtErrors.push(tag);
      var c = document.querySelector('[data-pick=seguranca]'); if (!c) return; c.click();
      var i = document.querySelector('.pc-field input[name=branch]'); if (!i || !document.querySelector('.pc-preview mark')) return;
      i.value = 'teste-do-sensor'; i.dispatchEvent(new Event('input', { bubbles: true }));
      if (document.querySelector('.pc-preview').textContent.indexOf('teste-do-sensor') >= 0) window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1); }, 2500);"; wait_s=5; fi
    # fixed groups, no item lost (18, with Configurações and without the Sites PHP shortcut) and the Agentes group collapses and comes back
    # keyboard focus stays on the group header after collapsing
    # the palette (⌘K) opens and lists: it was the only part of the old app.mjs without a script
    if [ "$route" = "#/overview" ]; then extra="setTimeout(function () {
      var ids = Array.prototype.map.call(document.querySelectorAll('.nav-group'), function (g) { return g.dataset.group; }).join(',');
      if (ids !== 'geral,projetos,ambiente,agentes,organizar,ajuda') window.__vtErrors.push('grupos: ' + ids);
      var n = document.querySelectorAll('#nav .nav-item').length; if (n !== 18) window.__vtErrors.push('itens na barra: ' + n);
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
      setTimeout(function () { if (document.querySelectorAll('.pal-item').length) window.__vtErrors.splice(window.__vtErrors.indexOf(pal), 1); }, 800); }, 2500);"; wait_s=6; fi
    # every sidebar item has its card and its hint; the empty terminal panel does not cover the page
    if [ "$route" = "#/inicio" ]; then extra="setTimeout(function () {
      Array.prototype.forEach.call(document.querySelectorAll('#nav .nav-item'), function (n) {
        if (!n.title) window.__vtErrors.push('item sem dica: ' + n.textContent.trim());
        var h = n.getAttribute('href'); var has = Array.prototype.some.call(document.querySelectorAll('.in-area'), function (c) { return c.getAttribute('href') === h; }); if (h !== '#/inicio' && !has) window.__vtErrors.push('item sem cartão: ' + h); });
      var tp = document.getElementById('term-panel'); if (tp.classList.contains('is-open') || tp.getBoundingClientRect().height > 40) window.__vtErrors.push('painel de terminal vazio aberto'); }, 3000);"; fi
    # Settings: hiding an item takes it out of the sidebar and survives a reload; showing all brings it back; Settings cannot be hidden
    if [ "$route" = "#/config" ]; then extra="var tag = 'esconder item nas Configurações'; window.__vtErrors.push(tag); setTimeout(function () {
      var box = document.querySelector('[data-side=tags]'); box.click();
      if (!document.querySelector('[data-side=config]').disabled) window.__vtErrors.push('Configurações pode ser escondida');
      setTimeout(function () {
        var still = Array.prototype.some.call(document.querySelectorAll('#nav .nav-item'), function (n) { return n.getAttribute('href') === '#/tags'; }); if (still) window.__vtErrors.push('item escondido continua na barra');
        else window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1);
        document.querySelector('[data-cf-action=sidebar-reset]').click(); }, 900); }, 2500);
      setTimeout(function () { if (document.querySelector('#app.is-offline')) window.__vtErrors.push('aviso de servidor indisponível com o servidor no ar'); }, 5500);"; wait_s=6; fi
    lerd_env "dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --snapshot "$shot" --route "$route" --wait "$wait_s" \
      --eval "$(expect "${pair#*|}") $CLIP_JS $extra" || { lerd_ok=1; echo "falhou com Lerd simulado: $route"; lerd_diag; break; }
  done
  # Node project registered through the page's own API (read-only fixture) and opened on its own screen
  if [ "$lerd_ok" -eq 0 ]; then
    NODE_JS="import('./js/api.mjs').then(function (m) { return m.post('/api/node-projects', { path: '$ROOT/tests/fixtures/node/painel', name: 'painel' }); })
      .then(function () { window.dispatchEvent(new CustomEvent('vulcan-node-changed')); location.hash = '#/node/painel'; }, function (e) { window.__vtErrors.push('node: ' + e.message); });"
    lerd_env "dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --snapshot "$TMP_ROOT/lerd-node.png" --route "#/node" --wait 5 \
      --eval "$NODE_JS $(expect "'.np-scripts', '.np-supabase', '.np-vercel', '#node-list .site-item'") $CLIP_JS" \
      || { lerd_ok=1; echo "falhou com Lerd simulado: #/node/painel"; }
  fi
  # no control out of the window, no horizontal scroll and targets at the minimum, from the smallest accepted width to the default window
  if [ "$lerd_ok" -eq 0 ]; then
    for size in 900x640 1280x820 1320x840; do
      for route in "#/sites/loja/terminal" "#/overview" "#/config" "#/codigo"; do
        lerd_env "dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --size "$size" --snapshot "$TMP_ROOT/largura.png" --route "$route" --wait 4 \
          --eval "$(cat tests/tools/sensor_larguras.js)" || { lerd_ok=1; echo "falhou em $size: $route"; }
      done
    done
    TASKS_JS="import('./js/api.mjs').then(function (m) { return m.post('/api/tasks', { title: 'Revisar o fluxo de pagamento com um nome bem longo que precisa caber', tags: ['etiqueta-longa'], priority: 1, assignee: 'alguem', due: '2026-12-01' }); }).then(function () { location.hash = '#/tasks'; });"
    lerd_env "dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --size 900x640 --snapshot "$TMP_ROOT/largura.png" --route "#/overview" --wait 5 \
      --eval "$TASKS_JS $(cat tests/tools/sensor_larguras.js)" || { lerd_ok=1; echo "falhou: tarefas em 900 px"; }
  fi
  kill "$LERD_API_PID" 2>/dev/null || true
  wait "$LERD_API_PID" 2>/dev/null || true
  [ "$lerd_ok" -eq 0 ] || exit 1

  step "texto digitado sobrevive à mudança da lista de sites"
  # fake API with a site that appears and disappears every 3 s; the Prompts composer field must keep its text
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
    "dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --snapshot "$TMP_ROOT/lerd-alterna.png" --route "#/prompts" \
    --wait 16 --eval "$KEEP_JS" || alt_ok=1
  # the Logs tab of a site that leaves the list: an empty state with the message, never an error on its own
  LOGS_JS="(function () { var tag = 'aba Logs sem o estado vazio do site que saiu'; window.__vtErrors.push(tag);
    var t = setInterval(function () { var e = document.querySelector('.logs-body .empty-block h3, .page .empty-block h3');
      if (e && /alterna/.test(e.textContent)) { clearInterval(t); window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1); } }, 200); })();"
  isolated_env VULCAN_LERD_BIN="$ROOT/tests/tools/fake-lerd" VULCAN_LERD_API="http://127.0.0.1:$(cat "$TMP_ROOT/lerd-alterna.port")" \
    "dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --snapshot "$TMP_ROOT/lerd-alterna-logs.png" --route "#/sites/alterna/logs" \
    --wait 12 --eval "$LOGS_JS" || alt_ok=2
  isolated_env "dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --snapshot "$TMP_ROOT/logs-sem-site.png" --route "#/sites/nao-existe/logs" \
    --wait 3 --eval "$(expect "'.page .empty-block h3'")" || alt_ok=3
  kill "$ALT_PID" 2>/dev/null || true
  wait "$ALT_PID" 2>/dev/null || true
  [ "$alt_ok" -eq 0 ] || { echo "falhou: telas com a lista de sites mudando ($alt_ok)"; exit 1; }

  step "janela presa à origem do app"
  # another origin that really responds: without the navigation policy the window would go there and the snapshot exits with 4
  mkdir -p "$TMP_ROOT/fora" && echo '<html><body>fora</body></html>' > "$TMP_ROOT/fora/index.html"
  "$PY" -c 'import http.server, functools, sys
h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=sys.argv[1])
s = http.server.HTTPServer(("127.0.0.1", 0), h); print(s.server_port, flush=True); s.serve_forever()' \
    "$TMP_ROOT/fora" > "$TMP_ROOT/fora.port" 2>/dev/null &
  FORA_PID=$!
  for _ in 1 2 3 4 5 6 7 8 9 10; do [ -s "$TMP_ROOT/fora.port" ] && break; sleep 0.3; done
  fora="http://127.0.0.1:$(cat "$TMP_ROOT/fora.port")/"
  nav_ok=0
  isolated_env "dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --snapshot "$TMP_ROOT/snapshot-fora.png" \
    --route "#/overview" --wait 3 --eval "location.href = '$fora'" || nav_ok=$?
  kill "$FORA_PID" 2>/dev/null || true
  wait "$FORA_PID" 2>/dev/null || true
  [ "$nav_ok" -eq 0 ] || { echo "a janela saiu do app ou falhou (saída $nav_ok)"; exit 1; }

  step "servidor não importa módulo da pasta atual"
  mkdir -p "$TMP_ROOT/hostil"
  printf "open(%s, 'w').write('x')\n" "'$TMP_ROOT/importou'" > "$TMP_ROOT/hostil/secrets.py"
  app_bin="$ROOT/dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox"
  (cd "$TMP_ROOT/hostil" && isolated_env "$app_bin" --snapshot "$TMP_ROOT/snapshot-hostil.png" --wait 2)
  [ ! -e "$TMP_ROOT/importou" ] || { echo "o servidor importou secrets.py da pasta atual"; exit 1; }

  if [ -f scripts/install_app.sh ]; then
    step "instalação em diretórios temporários, com o app de nome antigo presente"
    mkdir -p "$TMP_ROOT/Applications/Vulcan Terminal.app/Contents" "$TMP_ROOT/Desktop"
    touch "$TMP_ROOT/Applications/Vulcan Terminal.app/Contents/marca"
    ln -s "$TMP_ROOT/Applications/Vulcan Terminal.app" "$TMP_ROOT/Desktop/Vulcan Terminal"
    VULCAN_NO_FINDER=1 VULCAN_INSTALL_DEST="$TMP_ROOT/Applications" VULCAN_DESKTOP="$TMP_ROOT/Desktop" \
      bash scripts/install_app.sh
    [ ! -e "$TMP_ROOT/Applications/Vulcan Terminal.app" ] || { echo "o app de nome antigo continuou instalado"; exit 1; }
    ls "$TMP_ROOT/Applications"/Vulcan\ Terminal\ \(anterior*/Contents/marca >/dev/null || { echo "o app antigo não foi preservado"; exit 1; }
    [ ! -L "$TMP_ROOT/Desktop/Vulcan Terminal" ] || { echo "o atalho antigo continuou na Mesa"; exit 1; }
    target="$(readlink "$TMP_ROOT/Desktop/Vulcan Celox")"
    [ "$target" = "$TMP_ROOT/Applications/Vulcan Celox.app" ] || { echo "atalho aponta para $target"; exit 1; }
    isolated_env "$TMP_ROOT/Desktop/Vulcan Celox/Contents/MacOS/vulcan-celox" --snapshot "$TMP_ROOT/snapshot-atalho.png" --wait 2
    [ "$(stat -f %z "$TMP_ROOT/snapshot-atalho.png")" -gt 20000 ] || { echo "snapshot pelo atalho falhou"; exit 1; }
  fi
fi

printf '\nVALIDATE OK\n'
