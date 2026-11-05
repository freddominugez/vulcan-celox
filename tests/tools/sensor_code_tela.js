// Sensor of the Code screen in the real app: tree, each state of the viewer, keyboard and file name as text.
// Reads window.__ROOT, defined by the caller. Starts as a pending error and leaves the list when it reaches the end.
(function () {
  var tag = 'tela Code incompleta'; window.__vtErrors.push(tag);
  var fail = function (m) { window.__vtErrors.push('tela Code: ' + m); };
  var ROOT = window.__ROOT;
  function row(name) {
    return Array.prototype.find.call(document.querySelectorAll('.ce-tree .wb-row'), function (r) { return r.querySelector('.wb-title') && r.querySelector('.wb-title').textContent === name; });
  }
  function click(name) { var r = row(name); if (!r) { fail('sem a linha ' + name); return; } r.querySelector('.wb-title').click(); }
  function empty() { var h = document.querySelector('.code-body .code-empty h3'); return h ? h.textContent : ''; }
  function text() { var c = document.querySelector('.code-body .cm-content'); return c ? c.textContent : ''; }
  var steps = [
    function () { return row('src') && row('.env') && row('link-fora'); },
    function () {
      if (!row('<img src=x onerror=window.__xss=1>.php')) fail('nome de arquivo com HTML não apareceu como texto');
      if (document.querySelector('.ce-tree img')) fail('nome de arquivo virou HTML');
      if (row('.git')) fail('.git à vista');
      click('.env'); return true; },
    function () { if (!/sens/i.test(empty())) return false;
      if (document.querySelector('[data-ce-view=editor]')) fail('arquivo sensível oferece Abrir no editor');
      click('grande.txt'); return true; },
    function () { if (!/1 MB/.test(empty())) return false; click('binario.bin'); return true; },
    function () { if (!/bin/i.test(empty())) return false; click('link-fora'); return true; },
    function () { if (!/link/i.test(empty())) return false; click('<img src=x onerror=window.__xss=1>.php'); return true; },
    function () { if (text().indexOf('<script>') < 0) return false; if (window.__xss) fail('conteúdo interpretado'); click('README.md'); return true; },
    function () { if (text().indexOf('Projeto') < 0) return false; document.querySelector('[data-ce-mode=diff]').click(); return true; },
    function () { if (!document.querySelector('.code-body .code-empty [data-ce-mode=file]')) return false; document.querySelector('.code-body .code-empty [data-ce-mode=file]').click(); return true; },
    function () { if (text().indexOf('Projeto') < 0) return false; click('src'); return true; },
    function () { if (!row('mod1.js')) return false;
      if (row('node_modules') && !row('node_modules').classList.contains('ce-ignored')) fail('node_modules sem a marca de ignorado');
      click('vazia'); return true; },
    function () { click('longo.txt'); return true; },
    function () { if (text().indexOf('linha 1') < 0) return false;
      var tree = document.querySelector('.ce-tree .wunderbaum'); var before = document.querySelector('.code-path').textContent;
      tree.focus();
      tree.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }));
      window.__ceBefore = before; return true; },
    function () { document.querySelector('.ce-tree .wunderbaum').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); return true; },
    function () { var p = document.querySelector('.code-path').textContent; if (p === window.__ceBefore) return false;
      if (p !== 'link-fora') fail('setas e Enter abriram ' + p); return true; },
    function () {
      if (document.documentElement.scrollWidth > window.innerWidth) fail('estourou a largura');
      var bar = document.querySelector('.ce-top').getBoundingClientRect(); if (bar.right > window.innerWidth + 1) fail('barra cortada');
      var tree = document.querySelector('.ce-side').getBoundingClientRect(); if (tree.width < 170) fail('árvore estreita demais: ' + tree.width);
      var main = document.querySelector('.ce-main').getBoundingClientRect(); if (main.right > window.innerWidth + 1) fail('visor cortado');
      window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1); return true; },
  ];
  var i = 0;
  import('./js/api.mjs').then(function (m) { return m.post('/api/files/roots', { path: ROOT }); }).then(function () {
    location.hash = '#/codigo/' + encodeURIComponent(ROOT);
    var t = setInterval(function () { if (i >= steps.length) return clearInterval(t); if (steps[i]()) i += 1; }, 120);
  }).catch(function (e) { fail(e.message || e); });
})();
