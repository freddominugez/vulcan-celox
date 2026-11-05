// Light theme on a site's page: the tabs follow the page, and every text in them has a readable contrast.
(function () {
  var tag = 'aba Tarefas no tema claro não verificada'; window.__vtErrors.push(tag);
  function lum(c) { var v = c.map(function (x) { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }); return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; }
  function rgb(s) { return s.match(/[0-9.]+/g).map(Number); }
  function ground(el) { while (el) { var c = rgb(getComputedStyle(el).backgroundColor); if (c.length < 4 || c[3] > 0) return c; el = el.parentElement; } return [255, 255, 255]; }
  import('./js/theme.mjs').then(function (m) { return m.setThemePref('claro'); }).then(function () {
    var t = setInterval(function () { var host = document.querySelector('.ws-child'); if (!host || !host.innerText.trim()) return; clearInterval(t);
      setTimeout(function () {
        if (document.querySelector('.ws-body.is-terminal')) window.__vtErrors.push('a aba Tarefas ficou no escopo escuro do terminal');
        var walk = document.createTreeWalker(host, NodeFilter.SHOW_TEXT), n, seen = 0;
        while ((n = walk.nextNode())) { var el = n.parentElement; if (!n.textContent.trim() || !el.offsetParent || el.closest('button:disabled')) continue; seen += 1;
          var a = lum(rgb(getComputedStyle(el).color)), b = lum(ground(el)), r = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
          if (r < 3) window.__vtErrors.push('texto com contraste ' + r.toFixed(2) + ': ' + n.textContent.trim().slice(0, 40)); }
        if (seen) window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1); }, 700); }, 150);
  }).catch(function (e) { window.__vtErrors.push('tema claro: ' + (e.message || e)); });
})();
