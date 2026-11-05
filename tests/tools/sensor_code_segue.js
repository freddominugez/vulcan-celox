// Sensor of following on the Code screen: a fake agent writes and records it, another program writes without a record. Reads window.__ROOT.
(function () {
  var tag = 'acompanhar na tela Code incompleto'; window.__vtErrors.push(tag);
  var fail = function (m) { window.__vtErrors.push('acompanhar: ' + m); };
  var ROOT = window.__ROOT;
  function row(name) { return Array.prototype.find.call(document.querySelectorAll('.ce-tree .wb-row'), function (r) { var t = r.querySelector('.wb-title'); return t && t.textContent === name; }); }
  function shown() { var p = document.querySelector('.code-path'); return p ? p.textContent : ''; }
  function text() { var c = document.querySelector('.code-body .cm-content'); return c ? c.textContent : ''; }
  function status() { var s = document.querySelector('.ce-status-who'); return s ? s.textContent : ''; }
  var button = function () { return document.querySelector('[data-ce=follow]'); };
  var steps = [
    function () { return row('src') && !button().classList.contains('is-paused'); },
    function () { if (shown() !== 'passo-1.py' || text().indexOf('linha 0') < 0) return false;
      var seen = Date.now();
      import('./js/api.mjs').then(function (m) { return m.get('/api/files/read?root=' + encodeURIComponent(ROOT) + '&path=passo-1.py'); }).then(function (d) {
        var m = /gravado = (\d+)/.exec(d.text); var atraso = m ? seen - Number(m[1]) : -1;
        window.__ceAtraso = atraso;
        if (atraso < 0 || atraso > 2000) fail('a escrita do agente levou ' + atraso + ' ms até o visor'); });
      return true; },
    function () { var r = row('passo-1.py'); if (!r || !r.querySelector('.ce-who-claude')) return false;
      if (status().indexOf('Claude Code') < 0) fail('status sem o agente: ' + status());
      document.querySelector('.code-body').dispatchEvent(new WheelEvent('wheel', { bubbles: true, deltaY: 40 }));
      if (!button().classList.contains('is-paused')) fail('rolar não pausou'); return true; },
    function () { if (!row('passo-2.py')) return false;
      if (shown() !== 'passo-1.py') fail('o visor mudou de arquivo durante a pausa');
      button().click(); return true; },
    function () { if (shown() !== 'passo-2.py' || text().indexOf('linha 0') < 0) return false;
      if (button().classList.contains('is-paused')) fail('um clique não retomou'); return true; },
    function () { if (shown() !== 'externo.txt') return false;
      if (/Claude|Codex/.test(status()) || !status()) fail('escrita externa com autor: ' + status());
      if (row('externo.txt').querySelector('.ce-who')) fail('marca de agente em escrita externa');
      return true; },
    function () { var r = row('.env.novo'); if (!r || !r.querySelector('.ce-mark').dataset.mark) return false; window.__ceEnv = Date.now(); return true; },
    function () { if (Date.now() - window.__ceEnv < 1500) return false;
      if (shown() !== 'externo.txt') fail('o acompanhamento foi a um arquivo sensível: ' + shown());
      window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1); return true; },
  ];
  var i = 0;
  Object.defineProperty(document, 'hidden', { configurable: true, get: function () { return false; } });
  import('./js/api.mjs').then(function (m) { return m.post('/api/files/roots', { path: ROOT }); }).then(function () {
    location.hash = '#/codigo/' + encodeURIComponent(ROOT);
    var t = setInterval(function () { if (i >= steps.length) return clearInterval(t); if (steps[i]()) i += 1; }, 100);
    setTimeout(function () { if (i < steps.length) fail('parou no passo ' + i + ', visor em ' + shown() + ', estado ' + status() + ', botão ' + button().textContent); }, 24500);
  }).catch(function (e) { fail(e.message || e); });
})();
