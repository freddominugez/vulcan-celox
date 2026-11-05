// Panel shortcuts in the real app. Reads window.__ROOT, a project folder for the Code screen.
// 1. ⌘J on Terminais, where the bottom panel is hidden, shows a short message.
// 2. ⇧⌘D (the menu command) detaches the active terminal of the bottom panel.
// 3. On the Code screen, ⌘F opens the viewer's search and not the terminal's.
(function () {
  var tag = 'atalhos do painel incompletos'; window.__vtErrors.push(tag);
  var fail = function (m) { window.__vtErrors.push('atalhos: ' + m); };
  function cmd(key, shift) { document.dispatchEvent(new KeyboardEvent('keydown', { key: key, metaKey: true, ctrlKey: true, shiftKey: Boolean(shift), bubbles: true })); }
  var fase = 0, popped = null, pool = null;
  Promise.all([import('./js/terminal-pool.mjs'), import('./js/api.mjs')]).then(function (m) {
    pool = m[0].terminals; var original = pool.popout.bind(pool);
    pool.popout = function (id) { popped = id; };
    return m[1].post('/api/files/roots', { path: window.__ROOT });
  }).then(function () { location.hash = '#/terminals'; }).catch(function (e) { fail('início: ' + (e.message || e)); });
  var t = setInterval(function () {
    if (fase === 0 && location.hash === '#/terminals' && document.querySelector('#toasts')) {
      setTimeout(function () { cmd('j'); }, 300); fase = 1;
    } else if (fase === 1 && /painel de baixo|bottom panel/.test(document.querySelector('#toasts').textContent)) {
      location.hash = '#/codigo/' + encodeURIComponent(window.__ROOT) + '/README.md'; fase = 2;
    } else if (fase === 2 && document.querySelector('.ce-main .cm-content') && document.querySelector('.ce-main .cm-content').textContent.indexOf('Projeto') >= 0) {
      import('./js/terminals.mjs').then(function (m) { return m.terminals.create({ cwd: window.__ROOT, title: 'atalhos' }); }).catch(function (e) { fail('terminal: ' + (e.message || e)); }); fase = 3;
    } else if (fase === 3 && document.querySelector('#term-panel .tab[data-id]')) {
      setTimeout(function () { window.vulcanCommand('popoutTerminal'); }, 300); fase = 4;
    } else if (fase === 4 && popped) {
      if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
      cmd('f'); fase = 5;
      setTimeout(function () {
        if (!document.querySelector('.ce-main .cm-search')) fail('⌘F não abriu a busca do visor');
        var bar = Array.prototype.find.call(document.querySelectorAll('.term-search-input'), function (i) { return i.offsetParent; });
        if (bar) fail('⌘F abriu também a busca do terminal');
        clearInterval(t); window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1);
      }, 500);
    }
  }, 200);
})();
