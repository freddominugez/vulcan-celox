// Sidebar rail in a 900 px window: starts collapsed, ⌘B opens it and the choice goes to the server, ⌘B collapses it again.
(function () {
  var tag = 'trilho da barra lateral incompleto'; window.__vtErrors.push(tag);
  var fail = function (m) { window.__vtErrors.push('trilho: ' + m); };
  var app = document.getElementById('app');
  function key() { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'b', metaKey: true, ctrlKey: true, shiftKey: true, bubbles: true })); }
  setTimeout(function () {
    if (!app.classList.contains('is-rail')) { fail('não começou recolhida'); return; }
    key();
    if (app.classList.contains('is-rail')) fail('⌘B não abriu a barra');
    setTimeout(function () {
      import('./js/api.mjs').then(function (m) { return m.patch('/api/preferences', {}); }).then(function (p) {
        if (p.sidebar_collapsed !== false) fail('a escolha não foi para o servidor: ' + p.sidebar_collapsed);
        key();
        if (!app.classList.contains('is-rail')) fail('⌘B não recolheu de novo');
        window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1);
      });
    }, 600);
  }, 2500);
})();
