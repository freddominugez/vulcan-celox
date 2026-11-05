// Sensor of the live Code screen: a real program writes on disk and the tree and the viewer show it in up to 2 s.
// Reads window.__ROOT. Scroll and selection stay, the changed line lights up, a deleted file keeps its content.
(function () {
  var tag = 'tela Code ao vivo incompleta'; window.__vtErrors.push(tag);
  var fail = function (m) { window.__vtErrors.push('ao vivo: ' + m); };
  var ROOT = window.__ROOT;
  function row(name) { return Array.prototype.find.call(document.querySelectorAll('.ce-tree .wb-row'), function (r) { var t = r.querySelector('.wb-title'); return t && t.textContent === name; }); }
  function mark(name) { var r = row(name); var m = r && r.querySelector('.ce-mark'); return m ? m.dataset.mark : ''; }
  function text() { var c = document.querySelector('.code-body .cm-content'); return c ? c.textContent : ''; }
  function scroller() { return document.querySelector('.code-body .cm-scroller'); }
  var steps = [
    function () { var r = row('longo.txt'); if (!r) return false; r.querySelector('.wb-title').click(); return true; },
    function () { if (text().indexOf('linha 1') < 0) return false; var s = row('src'); s.querySelector('.wb-title').click(); return true; },
    function () { if (!row('mod1.js')) return false;
      // reading: a gesture pauses following, and then the viewer does not move by itself
      document.querySelector('.code-body').dispatchEvent(new WheelEvent('wheel', { bubbles: true, deltaY: 40 }));
      var box = scroller(); box.scrollTop = 1500;
      var sel = getSelection(); var line = document.querySelectorAll('.code-body .cm-line')[3];
      var r = document.createRange(); r.selectNodeContents(line); sel.removeAllRanges(); sel.addRange(r);
      window.__ceEditor = document.querySelector('.code-body .cm-editor');
      window.__ceTop = null; return true; },
    function () { if (window.__ceTop === null) { window.__ceTop = scroller().scrollTop; if (window.__ceTop < 500) fail('rolagem não aplicada'); }
      if (mark('longo.txt') !== 'M') return false;
      var box = scroller();
      if (document.querySelector('.code-body .cm-editor') !== window.__ceEditor) fail('o editor foi recriado');
      if (Math.abs(box.scrollTop - window.__ceTop) > 40) fail('a rolagem mudou de ' + window.__ceTop + ' para ' + box.scrollTop);
      box.scrollTop = 0; return true; },
    function () { if (text().indexOf('gravado =') < 0 && !document.querySelector('.ce-changed-line')) return false;
      var m = /gravado = (\d+)/.exec(text()); var atraso = m ? Date.now() - Number(m[1]) : -1;
      if (!document.querySelector('.ce-changed-line')) fail('linha alterada sem destaque');
      if (atraso > 2000) fail('a escrita levou ' + atraso + ' ms até a tela');
      window.__ceAtraso = atraso; return true; },
    function () { return mark('novo-arquivo.js') === 'A'; },
    function () { if (mark('longo.txt') !== 'D') return false;
      if (!document.querySelector('.ce-gone')) fail('sem o aviso de arquivo apagado');
      if (text().indexOf('linha 1') < 0) fail('o último conteúdo sumiu');
      return true; },
    function () { if (mark('renomeado.bin') !== 'A' || mark('binario.bin') !== 'D') return false;
      var s = row('src'); s.querySelector('.wb-expander').click(); return true; },
    function () { if (row('mod1.js')) return false; if (mark('src') !== '•') { fail('pasta recolhida sem o ponto: ' + mark('src')); }
      if (document.querySelector('.toast.is-error')) fail('mensagem de erro na tela');
      if (document.querySelector('.ce-tree img')) fail('HTML na árvore');
      window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1); return true; },
  ];
  var i = 0;
  Object.defineProperty(document, 'hidden', { configurable: true, get: function () { return false; } });
  import('./js/api.mjs').then(function (m) { return m.post('/api/files/roots', { path: ROOT }); }).then(function () {
    location.hash = '#/codigo/' + encodeURIComponent(ROOT);
    var t = setInterval(function () { if (i >= steps.length) return clearInterval(t); if (steps[i]()) i += 1; }, 100);
  }).catch(function (e) { fail(e.message || e); });
})();
