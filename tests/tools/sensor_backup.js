// Settings, Backup section: a backup made by the app is checked before restoring, and a hand-made zip cannot be
// restored. The restore copies are listed with their button. Expects window.__BKDIR (folder for the backup),
// window.__BADZIP (zip with a refused member) and one copy in .restauros of the data folder.
(function () {
  var tag = 'resumo do backup incompleto';
  window.__vtErrors.push(tag);
  function fail(m) { window.__vtErrors.push(m); }
  function zip(path) {
    var input = document.querySelector('[data-role=zip]');
    input.value = path;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    document.querySelector('[data-data=inspect]').click();
  }
  var fase = 0, made = null;
  import('./js/api.mjs').then(function (m) { return m.post('/api/data/backup', { folder: window.__BKDIR }); }).then(function (r) {
    made = r.created.path;
    location.hash = '#/config';
  }).catch(function (e) { fail('backup: ' + (e.message || e)); });
  var t = setInterval(function () {
    if (!made || !document.querySelector('[data-data=inspect]')) return;
    if (fase === 0) {
      if (document.querySelector('[data-data=restore]')) fail('Restaurar à vista antes de conferir');
      if (!document.querySelector('.cf-restore [data-data=trash-restore]')) fail('cópia de restauração não listada');
      zip(window.__BADZIP); fase = 1;
    } else if (fase === 1 && document.querySelector('.cf-check[data-ok="0"]')) {
      var bad = document.querySelector('.cf-check');
      if (bad.querySelector('[data-data=restore]')) fail('zip recusado deixou restaurar');
      if (!bad.querySelector('.cf-check-error')) fail('zip recusado sem o motivo');
      zip(made); fase = 2;
    } else if (fase === 2 && document.querySelector('.cf-check[data-ok="1"]')) {
      var box = document.querySelector('.cf-check');
      if (!box.querySelector('[data-data=restore]')) fail('sem o botão Restaurar depois de conferir');
      if (box.querySelectorAll('.cf-check-counts li').length < 6) fail('contagens incompletas no resumo');
      if (box.getBoundingClientRect().right > window.innerWidth) fail('resumo saiu da janela');
      document.querySelector('.cf-restore [data-data=trash-restore]').click(); fase = 3;
    } else if (fase === 3 && document.querySelector('.dialog')) {
      document.querySelector('.dialog [data-answer=no]').click();
      if (!document.querySelector('.cf-restore')) fail('cancelar tirou a cópia da lista');
      if (document.documentElement.scrollWidth > window.innerWidth) fail('Configurações estourou a largura');
      document.querySelector('.cf-check').scrollIntoView({ block: 'center' });
      clearInterval(t);
      window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1);
    }
  }, 150);
})();
