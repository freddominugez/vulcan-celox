# Sensores de navegador da aba Código, do terminal e dos temas. Carregado por scripts/validate.sh, que define
# isolated_env, step, CLIP_JS, TMP_ROOT e PY.

# cada seletor começa como erro pendente e sai da lista quando aparece; o snapshot falha (3) se algum faltar
expect() {
  printf '%s' "[$1].forEach(function (s) { var tag = 'ausente: ' + s; window.__vtErrors.push(tag);
    var t = setInterval(function () { if (document.querySelector(s)) { var i = window.__vtErrors.indexOf(tag);
      if (i >= 0) window.__vtErrors.splice(i, 1); clearInterval(t); } }, 150); });"
}
step "CodeMirror vendorizado carrega com a CSP do app"
# aparece como erro pendente até o visor, o diff e cada linguagem montarem de verdade no WKWebView
CM_JS="(function () { var tag = 'CodeMirror não montou'; window.__vtErrors.push(tag);
  var s = document.createElement('script'); s.src = 'vendor/codemirror.js';
  s.onerror = function () { window.__vtErrors.push('vendor/codemirror.js recusado'); };
  s.onload = function () { var C = window.CM, box = document.createElement('div'); document.body.appendChild(box);
    var langs = [C.php(), C.javascript({ typescript: true }), C.python(), C.html(), C.css(), C.json(), C.markdown(), C.sql(), C.yaml()];
    langs.forEach(function (l) { new C.EditorView({ parent: box, state: C.EditorState.create({ doc: '<b>x</b>',
      extensions: [C.lineNumbers(), C.search(), C.syntaxHighlighting(C.defaultHighlightStyle), l, C.EditorState.readOnly.of(true)] }) }); });
    new C.MergeView({ parent: box, a: { doc: 'um' }, b: { doc: 'dois' } });
    if (box.querySelectorAll('.cm-editor').length === langs.length + 2 && box.querySelector('.cm-changedLine, .cm-changedText, .cm-mergeView')) {
      window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1); }
    box.remove(); };
  document.head.appendChild(s); })();"
shot="$TMP_ROOT/snapshot-codemirror.png"
isolated_env "dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --snapshot "$shot" --route "#/overview" --wait 3 --eval "$CM_JS"

step "aba Código: árvore, arquivo, diff e nome de arquivo como texto"
CODE_SID="cccccccc-dddd-4eee-8fff-000000000001"
"$PY" -I tests/tools/code_fixture.py "$TMP_ROOT/code"
CODE_JS="(function () { var tag = 'aba Código incompleta'; window.__vtErrors.push(tag); var fase = 0;
  var t = setInterval(function () {
    if (fase === 0 && document.querySelector('.code-tree .code-file') && document.querySelector('.code-body .cm-editor')) {
      fase = 1;
      var hostil = Array.prototype.find.call(document.querySelectorAll('.code-file'), function (b) { return b.textContent.indexOf('<img src=x') >= 0; });
      if (!hostil) window.__vtErrors.push('nome de arquivo com HTML não apareceu como texto');
      else hostil.click();
    } else if (fase === 1 && document.querySelector('.code-body .cm-content') && document.querySelector('.code-body .cm-content').textContent.indexOf('<script>') >= 0) {
      fase = 2; document.querySelector('[data-mode=diff]').click();
    } else if (fase === 2 && document.querySelector('.cm-mergeView')) {
      fase = 3;
      var env = Array.prototype.find.call(document.querySelectorAll('.code-file'), function (b) { return b.textContent.indexOf('.env') >= 0; });
      if (env) env.click();
    } else if (fase === 3 && document.querySelector('.code-empty h3') && document.querySelector('.code-empty h3').textContent.indexOf('sensível') >= 0) {
      clearInterval(t);
      if (document.querySelector('.code-tree img, .code-body img') || window.__xss) window.__vtErrors.push('HTML de arquivo foi interpretado');
      if (document.documentElement.scrollWidth > window.innerWidth) window.__vtErrors.push('aba Código estourou a largura');
      window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1);
    }
  }, 150); })();"
isolated_env env CLAUDE_CONFIG_DIR="$TMP_ROOT/code/claude" "dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --snapshot "$TMP_ROOT/snapshot-codigo.png" --route "#/agentes/$CODE_SID/codigo" --wait 7 --eval "$CODE_JS"
# sessão cujos arquivos não existem nesta máquina: estados vazios, sem erro de console
isolated_env "dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --snapshot "$TMP_ROOT/snapshot-codigo-vazio.png" --route "#/agentes/11111111-2222-4333-8444-555555555555/codigo" --wait 4 --eval "$(expect "'.code-shell', '.code-tree', '.code-empty'")"

step "aba Código segue o agente, pausa ao rolar e retoma"
"$PY" -I tests/tools/code_fixture.py "$TMP_ROOT/code2"
( for n in 1 2 3; do sleep 6; "$PY" -I tests/tools/code_fixture.py "$TMP_ROOT/code2" crescer "$n"; done ) &
GROW_PID=$!
# com a tela do Mac inativa a janela fica oculta e o app para de consultar o servidor, de propósito; aqui ela conta como
# visível (no modo --snapshot, a casca também não deixa o WebKit suspender a página)
UNHIDE_JS="Object.defineProperty(document, 'hidden', { configurable: true, get: function () { return false; } });"
FOLLOW_JS="$UNHIDE_JS(function () {
  var tag = 'seguir o agente incompleto'; window.__vtErrors.push(tag); var fase = 0;
  function shown() { var p = document.querySelector('.code-path'); return p ? p.textContent : ''; }
  function text() { var c = document.querySelector('.code-body .cm-content'); return c ? c.textContent : ''; }
  function inTree(n) { return Array.prototype.some.call(document.querySelectorAll('.code-file'), function (b) { return b.textContent.indexOf(n) >= 0; }); }
  var t = setInterval(function () {
    if (fase === 0 && shown().indexOf('passo-1.py') >= 0 && text().indexOf('valor = 1') >= 0) {
      var m = /gravado = (\d+)/.exec(text()); var atraso = m ? Date.now() - Number(m[1]) : -1;
      if (atraso < 0 || atraso > 5000) window.__vtErrors.push('edição levou ' + atraso + ' ms até a tela');
      if (!document.querySelector('.code-follow.is-following')) window.__vtErrors.push('sem o aviso de seguindo');
      document.querySelector('.code-body').dispatchEvent(new WheelEvent('wheel', { bubbles: true, deltaY: 40 }));
      if (!document.querySelector('[data-code=resume]')) window.__vtErrors.push('rolar não pausou');
      window.__vtSel = document.querySelectorAll('.code-body .cm-selectionBackground').length; fase = 1;
    } else if (fase === 1 && inTree('passo-2.py')) {
      if (shown().indexOf('passo-1.py') < 0) window.__vtErrors.push('o visor mudou de arquivo durante a pausa');
      if (!window.__vtSel || !document.querySelector('.code-body .cm-selectionBackground')) window.__vtErrors.push('a seleção se perdeu durante a pausa');
      document.querySelector('[data-code=resume]').click(); fase = 2;
    } else if (fase === 2 && shown().indexOf('passo-2.py') >= 0 && text().indexOf('valor = 2') >= 0 && document.querySelector('.code-follow.is-following')) {
      fase = 3;
    } else if (fase === 3 && shown().indexOf('passo-3.py') >= 0 && text().indexOf('valor = 3') >= 0) {
      clearInterval(t); window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1);
    }
  }, 100); })();"
isolated_env env CLAUDE_CONFIG_DIR="$TMP_ROOT/code2/claude" "dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --snapshot "$TMP_ROOT/snapshot-seguir.png" --route "#/agentes/$CODE_SID/codigo" --wait 30 --eval "$FOLLOW_JS"
wait "$GROW_PID"

step "⌘-clique em caminho: reconhece no xterm de verdade, resolve no servidor e abre na linha"
"$PY" -I tests/tools/code_fixture.py "$TMP_ROOT/code3"
"$PY" -I tests/tools/code_fixture.py "$TMP_ROOT/code3" crescer 9
CODE3="$(cd "$TMP_ROOT/code3/projeto" && pwd -P)"
PATH_JS="(function () { var tag = 'caminho no terminal incompleto'; window.__vtErrors.push(tag);
  function fail(m) { window.__vtErrors.push(m); }
  Promise.all([import('./js/api.mjs'), import('./js/terminal-path-links.mjs')]).then(function (m) {
    return m[0].post('/api/terminals', { cwd: '$CODE3' }).then(function (tab) {
      var box = document.createElement('div'); box.style.cssText = 'position:fixed;left:-9999px;width:800px;height:200px'; document.body.appendChild(box);
      var term = new window.Terminal({ cols: 80, rows: 8 }); term.open(box);
      term.write('ver src/core/app.py:2 e .env e nao/existe.py e https://x.test/a.py fim\r\n', function () {
        var provider = m[1].pathLinkProvider(term, { modifier: function () { return true; },
          resolve: function (c) { return m[0].post('/api/code/resolve', { terminal: tab.id, candidates: c }).then(function (d) { return d.results; }); },
          activate: function () {} });
        provider.provideLinks(1, function (links) {
          links = links || [];
          if (links.length !== 2) return fail('links esperados: 2, vieram ' + links.length);
          if (links[0].text !== 'src/core/app.py:2' || links[0].range.start.x !== 5) fail('link no lugar errado: ' + links[0].text + ' em ' + links[0].range.start.x);
          if (links[1].text !== '.env') fail('.env deveria voltar marcado: ' + links[1].text);
          location.hash = '#/agentes/$CODE_SID/codigo/' + encodeURIComponent('$CODE3/passo-9.py') + '/390';
          var t = setInterval(function () { var c = document.querySelector('.code-body .cm-content'); var p = document.querySelector('.code-path');
            if (p && p.textContent.indexOf('passo-9.py') >= 0 && c && c.textContent.indexOf('# linha 389') >= 0) {
              clearInterval(t); window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1); } }, 150);
        });
      });
    });
  }).catch(function (e) { fail('caminho: ' + (e.message || e)); }); })();"
isolated_env env CLAUDE_CONFIG_DIR="$TMP_ROOT/code3/claude" "dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --snapshot "$TMP_ROOT/snapshot-caminho.png" --route "#/overview" --wait 7 --eval "$PATH_JS"

step "Linha do tempo por pedido: atalho e ida para o diff do turno"
TURN_JS="(function () { var tag = 'linha do tempo por pedido incompleta'; window.__vtErrors.push(tag); var fase = 0;
  var t = setInterval(function () {
    if (fase === 0 && document.querySelector('[data-tab=linha]')) { document.querySelector('[data-tab=linha]').click(); fase = 1; }
    else if (fase === 1 && document.querySelector('.turn .turn-diff')) {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', metaKey: true, ctrlKey: true, shiftKey: true, bubbles: true }));
      if (!document.activeElement || !document.activeElement.classList.contains('turn')) window.__vtErrors.push('⌘⇧↓ não foi para o pedido');
      if (document.querySelector('.turn img')) window.__vtErrors.push('nome de arquivo virou HTML na Linha do tempo');
      document.querySelector('.turn .turn-diff').click(); fase = 2;
    } else if (fase === 2 && document.querySelector('.cm-mergeView') && document.querySelector('[data-scope=turn].is-on')) {
      clearInterval(t); window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1);
    }
  }, 150); })();"
isolated_env env CLAUDE_CONFIG_DIR="$TMP_ROOT/code/claude" "dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --snapshot "$TMP_ROOT/snapshot-turnos.png" --route "#/agentes/$CODE_SID" --wait 6 --eval "$TURN_JS"

step "selo de porta na aba de um servidor de verdade"
PORT_JS="$UNHIDE_JS(function () { var tag = 'selo de porta não apareceu'; window.__vtErrors.push(tag);
  import('./js/terminals.mjs').then(function (m) { return m.terminals.create({ cwd: '$TMP_ROOT', title: 'portas', command: 'exec /usr/bin/python3 -m http.server 0 --bind 127.0.0.1' }); }).then(function () {
    var t = setInterval(function () { var b = document.querySelector('.port-badge');
      if (b && /^:\d+/.test(b.textContent)) { clearInterval(t);
        if (location.protocol !== 'http:' || location.hostname !== '127.0.0.1') window.__vtErrors.push('janela saiu da origem');
        window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1); } }, 200);
  }).catch(function (e) { window.__vtErrors.push('porta: ' + (e.message || e)); }); })();"
isolated_env "dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --snapshot "$TMP_ROOT/snapshot-porta.png" --route "#/terminals" --wait 16 --eval "$PORT_JS"

step "temas claro e escuro: telas principais sem estouro e com os tokens aplicados"
"$PY" -I tests/tools/code_fixture.py "$TMP_ROOT/code4"
for tema in claro escuro; do
  [ "$tema" = claro ] && fundo="rgb(250, 246, 238)" || fundo="rgb(7, 13, 24)"
  THEME_JS="document.documentElement.dataset.theme = '$tema'; setTimeout(function () {
    if (getComputedStyle(document.body).backgroundColor !== '$fundo') window.__vtErrors.push('tema $tema: fundo ' + getComputedStyle(document.body).backgroundColor);
    if (document.documentElement.scrollWidth > window.innerWidth) window.__vtErrors.push('tema $tema: estourou a largura'); }, 1500);"
  for route in "#/overview" "#/agentes" "#/agentes/$CODE_SID/codigo" "#/agentes/$CODE_SID" "#/tasks" "#/notes" "#/ajuda"; do
    shot="$TMP_ROOT/tema-$tema-$(printf '%s' "$route" | tr -c 'a-z0-9' '_').png"
    isolated_env env CLAUDE_CONFIG_DIR="$TMP_ROOT/code4/claude" "dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --snapshot "$shot" --route "$route" --wait 3 --eval "$THEME_JS $CLIP_JS"
  done
done

step "fonte Inter e logo: carregados de verdade, em cada tema o arquivo certo"
for tema in claro escuro; do
  [ "$tema" = claro ] && logo="primary" || logo="reverse"
  BRAND_JS="document.documentElement.dataset.theme = '$tema'; setTimeout(function () {
    var box = document.querySelector('.brand-logo'); if (!box) { window.__vtErrors.push('logo ausente'); return; }
    var img = Array.prototype.find.call(box.querySelectorAll('img'), function (i) { return getComputedStyle(i).display !== 'none'; });
    if (!img || img.src.indexOf('celox-logo-$logo') < 0) window.__vtErrors.push('logo errado no tema $tema: ' + (img ? img.src : 'nenhum'));
    else if (!img.naturalWidth || img.getBoundingClientRect().width < 280 || img.alt !== 'Vulcan Celox') window.__vtErrors.push('logo fora da regra');
    var mark = document.querySelector('.side-brand'); if (!mark || !mark.getAttribute('aria-label')) window.__vtErrors.push('símbolo sem nome acessível');
    var vis = Array.prototype.find.call(mark.querySelectorAll('img'), function (i) { return getComputedStyle(i).display !== 'none'; });
    if (!vis || !vis.naturalWidth) window.__vtErrors.push('símbolo não carregou');
    document.fonts.load('14px Inter').then(function (f) { if (!f.length || !document.fonts.check('14px Inter')) window.__vtErrors.push('Inter não carregou'); });
    if (getComputedStyle(document.body).fontFamily.indexOf('Inter') < 0) window.__vtErrors.push('Inter não é a fonte do app');
  }, 1200);"
  isolated_env "dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --snapshot "$TMP_ROOT/marca-$tema.png" --route "#/overview" --wait 3 --eval "$BRAND_JS"
done

step "interface em inglês: nenhuma tela com texto em português"
# os nomes vindos das fixtures são dados, não interface: o sensor olha o texto, tirando o que veio de sessão, site ou arquivo
EN_JS="$UNHIDE_JS setTimeout(function () {
  var pt = /[ãõç]|\b(para|sem|não|você|arquivo|arquivos|pasta|sessão|sessões|tarefas|nenhum|nenhuma|abrir|editar|ainda|pedido|pedidos|comandos)\b/i;
  var walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT), n, found = [];
  while ((n = walk.nextNode())) { var el = n.parentElement; if (!el || el.closest('script,style,.xterm,.cm-editor,.ag-first,.turn-ask,.ag-path,.code-dir,.ag-hit,.code-path,.mono')) continue;
    var s = n.textContent.trim(); if (s && pt.test(s) && !/^pedido \d+$/.test(s) && s.indexOf('/') !== 0) found.push(s.slice(0, 70)); }
  if (document.documentElement.lang !== 'en') found.push('lang=' + document.documentElement.lang);
  if (found.length) window.__vtErrors.push('português em ' + location.hash + ': ' + found.slice(0, 12).join(' | '));
}, 2500);"
for route in "#/inicio" "#/overview" "#/terminals" "#/agentes" "#/agentes/$CODE_SID" "#/agentes/$CODE_SID/codigo" "#/agentes/historico" "#/agentes/branches" "#/agentes/uso" "#/prompts" "#/tasks" "#/notes" "#/tags" "#/index" "#/ajuda" "#/lerd" "#/depuracao" "#/node"; do
  SENSOR_LANGUAGE=en isolated_env env CLAUDE_CONFIG_DIR="$TMP_ROOT/code4/claude" "dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --snapshot "$TMP_ROOT/en-$(printf '%s' "$route" | tr -c 'a-z0-9' '_').png" --route "$route" --wait 4 --eval "$EN_JS" || { echo "português em $route"; exit 1; }
done

step "novo terminal pelo diálogo: clique fora do cartão de tema não troca o tema"
DIALOG_JS="$UNHIDE_JS(function () { var tag = 'diálogo de novo terminal não abriu a aba'; window.__vtErrors.push(tag); var enviado = null;
  var original = window.fetch; window.fetch = function (u, o) { if (String(u) === '/api/terminals' && o && o.method === 'POST') enviado = JSON.parse(o.body); return original(u, o); };
  setTimeout(function () { window.vulcanCommand('newTerminalOptions'); }, 800);
  var fase = 0, t = setInterval(function () {
    var cartao = document.querySelector('.nt-theme');
    if (fase === 0 && cartao) { fase = 1; document.querySelector('.dialog .field-label').click(); document.querySelector('.dialog').click();
      setTimeout(function () { document.querySelector('.dialog button[type=submit]').click(); }, 900); }
    else if (fase === 1 && enviado) { fase = 2; if (enviado.theme === 'escuro' || enviado.theme === 'claro') window.__vtErrors.push('tema da página foi para a aba: ' + enviado.theme); }
    else if (fase === 2 && document.querySelector('.tab[data-id]')) { clearInterval(t); window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1); }
  }, 150); })();"
isolated_env "dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --snapshot "$TMP_ROOT/snapshot-dialogo.png" --route "#/terminals" --wait 7 --eval "$DIALOG_JS"

