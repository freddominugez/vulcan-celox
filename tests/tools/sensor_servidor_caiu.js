// The server process is killed from outside while the page is open. First load: the notice shows up with the cause,
// Show log and Restart server, and Restart is clicked. Second load, on the new server: the API answers.
(function () {
  if (window.VULCAN && window.VULCAN.restarted) {
    var back = 'servidor reiniciado não respondeu';
    window.__vtErrors.push(back);
    import('./js/api.mjs').then(function (m) { return m.get('/api/state'); }).then(function (s) {
      if (s && s.app) window.__vtErrors.splice(window.__vtErrors.indexOf(back), 1);
    }).catch(function (e) { window.__vtErrors.push('api depois do reinício: ' + (e.message || e)); });
    return;
  }
  var tag = 'aviso de servidor parado ou reinício ausente';
  window.__vtErrors.push(tag);
  var t = setInterval(function () {
    var box = document.getElementById('server-down');
    if (!box || !box.querySelector('[data-sd=log]') || !box.querySelector('[data-sd=restart]')) return;
    clearInterval(t);
    if (!/\d/.test(box.querySelector('.sd-title').textContent)) window.__vtErrors.push('aviso sem o código de saída');
    if (box.getBoundingClientRect().right > window.innerWidth) window.__vtErrors.push('aviso saiu da janela');
    box.querySelector('[data-sd=restart]').click();
  }, 200);
})();
