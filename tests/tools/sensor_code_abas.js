// Sensor of tabs, quick open and search on the Code screen. Reads window.__ROOT (no git) and window.__REPO (with git).
(function () {
  var tag = 'abas e busca da tela Code incompletas'; window.__vtErrors.push(tag);
  var fail = function (m) { window.__vtErrors.push('abas: ' + m); };
  function row(name) { return Array.prototype.find.call(document.querySelectorAll('.ce-tree .wb-row'), function (r) { var t = r.querySelector('.wb-title'); return t && t.textContent === name; }); }
  function shown() { var p = document.querySelector('.code-path'); return p ? p.textContent : ''; }
  function tabs() { return Array.prototype.map.call(document.querySelectorAll('.ce-tab-open'), function (t) { return t.textContent; }); }
  function key() { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'p', metaKey: navigator.platform.indexOf('Mac') >= 0, ctrlKey: navigator.platform.indexOf('Mac') < 0, shiftKey: navigator.platform.indexOf('Mac') < 0, bubbles: true })); }
  function type(el, v) { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); }
  function press(el, k) { el.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true })); }
  var api;
  var steps = [
    function () { if (!row('README.md')) return false; row('README.md').querySelector('.wb-title').click(); return true; },
    function () { if (shown() !== 'README.md') return false; row('longo.txt').querySelector('.wb-title').click(); return true; },
    function () { if (shown() !== 'longo.txt') return false;
      if (tabs().join() !== 'README.md,longo.txt') fail('abas: ' + tabs().join());
      document.querySelector('.ce-tab-open[data-tab-open="README.md"]').click(); return true; },
    function () { if (shown() !== 'README.md') return false;
      document.querySelector('[data-tab-close="README.md"]').click(); return true; },
    function () { if (shown() !== 'longo.txt') return false;
      if (tabs().join() !== 'longo.txt') fail('fechar: ' + tabs().join());
      key(); return true; },
    function () { var i = document.querySelector('.ce-quick input'); if (!i || !document.querySelector('.ce-quick-item')) return false;
      if (location.hash.indexOf('#/codigo') !== 0) fail('o atalho saiu da tela');
      type(i, 'chkot'); var first = document.querySelector('.ce-quick-item');
      if (!first || first.textContent !== 'src/core/Checkout.php') fail('filtro: ' + (first && first.textContent));
      type(i, '<img'); first = document.querySelector('.ce-quick-item');
      if (!first || document.querySelector('.ce-quick img')) fail('nome de arquivo virou HTML na lista');
      type(i, 'mod3'); press(i, 'Enter'); return true; },
    function () { if (shown() !== 'src/mod3.js') return false;
      if (document.querySelector('.ce-quick')) fail('a lista não fechou');
      document.querySelector('[data-ce=search]').click(); return true; },
    function () { var i = document.querySelector('.ce-searchform input'); if (!i || i.closest('[hidden]')) return false;
      i.value = 'Projeto'; i.form.requestSubmit(); return true; },
    function () { var n = document.querySelector('.ce-result-note'); if (!n || n.textContent.indexOf('Git') < 0) return false;
      document.querySelector('[data-ce=search]').click();
      window.__ceWas = tabs().length; location.hash = '#/codigo/' + encodeURIComponent(window.__REPO); return true; },
    function () { var r = document.querySelector('[data-ce-root]'); if (!r || r.value !== window.__REPO || !row('README.md')) return false;
      if (tabs().length) fail('abas de outra pasta apareceram');
      document.querySelector('[data-ce=search]').click();
      var i = document.querySelector('.ce-searchform input'); i.value = '-e'; i.form.requestSubmit(); return true; },
    function () { var n = document.querySelector('.ce-result-note'); if (n && n.textContent.indexOf('Nada') >= 0) { var i = document.querySelector('.ce-searchform input'); i.value = '<script>'; i.form.requestSubmit(); return true; } return false; },
    function () { var r = document.querySelector('.ce-result'); if (!r) return false;
      if (r.querySelector('script') || window.__xss) fail('linha de arquivo virou HTML na busca');
      var i = document.querySelector('.ce-searchform input'); i.value = 'linha 300'; i.form.requestSubmit(); window.__ceFirst = r; return true; },
    function () { var r = document.querySelector('.ce-result[data-rel="longo.txt"]'); if (!r) return false; r.click(); return true; },
    function () { var c = document.querySelector('.code-body .cm-content'); if (shown() !== 'longo.txt' || !c || c.textContent.indexOf('linha 300') < 0) return false;
      window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1); return true; },
  ];
  import('./js/views/code/explorer-tabs.mjs').then(function (m) {
    var list = []; for (var n = 0; n < 15; n++) list = m.addTab(list, 'f' + n);
    if (list.length !== 12 || list[11] !== 'f14' || list[0] !== 'f3') fail('limite de abas: ' + list.join());
    if (m.addTab(list, 'f5').length !== 12) fail('aba repetida'); });
  var i = 0;
  import('./js/api.mjs').then(function (m) { api = m; return Promise.all([m.post('/api/files/roots', { path: window.__ROOT }), m.post('/api/files/roots', { path: window.__REPO })]); }).then(function () {
    location.hash = '#/codigo/' + encodeURIComponent(window.__ROOT);
    var t = setInterval(function () { if (i >= steps.length) return clearInterval(t); if (steps[i]()) i += 1; }, 120);
    setTimeout(function () { if (i < steps.length) fail('parou no passo ' + i + ', visor em ' + shown()); }, 8500);
  }).catch(function (e) { fail(e.message || e); });
})();
