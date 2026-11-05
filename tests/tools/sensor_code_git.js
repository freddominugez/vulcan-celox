// Git marks in the Code screen tree, on the git repository of explorer_fixture.py: letter and color on each file, a dot on
// the folder with something inside, the deleted file struck through, the hint in full and the branch above the tree.
// Reads window.__ROOT. Also measures the contrast of each letter against the tree background.
(function () {
  var tag = 'marcas do Git incompletas'; window.__vtErrors.push(tag);
  var fail = function (m) { window.__vtErrors.push('marcas do Git: ' + m); };
  function row(name) {
    return Array.prototype.find.call(document.querySelectorAll('.ce-tree .wb-row'), function (r) { return r.querySelector('.wb-title') && r.querySelector('.wb-title').textContent === name; });
  }
  function mark(name) { var r = row(name); var m = r && r.querySelector('.ce-mark'); return m ? m : null; }
  function rgb(c) { var m = /rgba?\(([\d.]+), ([\d.]+), ([\d.]+)/.exec(c); return m ? [+m[1], +m[2], +m[3]] : null; }
  function lum(c) { return c.map(function (v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); })
    .reduce(function (a, v, i) { return a + v * [0.2126, 0.7152, 0.0722][i]; }, 0); }
  function background(el) { while (el) { var b = getComputedStyle(el).backgroundColor; if (b && !/rgba\(0, 0, 0, 0\)|transparent/.test(b)) return rgb(b); el = el.parentElement; } return [255, 255, 255]; }
  import('./js/api.mjs').then(function (m) { return m.post('/api/files/roots', { path: window.__ROOT }); }).then(function () {
    location.hash = '#/codigo/' + encodeURIComponent(window.__ROOT);
  }).catch(function (e) { fail('pasta: ' + (e.message || e)); });
  var t = setInterval(function () {
    var readme = mark('README.md'), novo = mark('novo.txt'), longo = mark('longo.txt'), src = mark('src');
    if (!readme || readme.dataset.mark !== 'M' || !novo || novo.dataset.mark !== 'U' || !longo || longo.dataset.mark !== 'D' || !src || src.dataset.mark !== '•') return;
    if (!document.querySelector('.ce-branch') || document.querySelector('.ce-branch').textContent.trim() !== 'main') return;
    clearInterval(t);
    [readme, novo, longo].forEach(function (m) {
      if (!m.textContent.trim()) fail('marca só com cor');
      if (!m.title || m.title.indexOf('Git') < 0) fail('dica sem o estado por extenso: ' + m.title);
      var fg = rgb(getComputedStyle(m).color), bg = background(m.closest('.wb-row'));
      var a = lum(fg), b = lum(bg), ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
      if (ratio < 4.5) fail('contraste ' + ratio.toFixed(2) + ' na letra ' + m.dataset.mark);
    });
    if (!row('longo.txt').querySelector('.ce-deleted')) fail('apagado sem risco');
    if (mark('Checkout.php')) fail('pasta recolhida mostrou o filho');
    if (mark('vazia') && mark('vazia').dataset.mark) fail('pasta vazia marcada: o Git não guarda pasta vazia');
    if (document.documentElement.scrollWidth > window.innerWidth) fail('tela estourou a largura');
    window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1);
  }, 200);
})();
