// In each width: no control out of the window, no horizontal scroll, targets at the minimum (28 px in dense bars and lists).
(function () {
  var tag = 'larguras não verificadas'; window.__vtErrors.push(tag);
  var fail = function (m) { window.__vtErrors.push(location.hash + ' em ' + window.innerWidth + ' px: ' + m); };
  setTimeout(function () {
    if (document.documentElement.scrollWidth > window.innerWidth) fail('rolagem horizontal');
    var view = document.getElementById('view').getBoundingClientRect();
    Array.prototype.forEach.call(document.querySelectorAll('.toolbar button, .toolbar a, .site-actions button, .site-actions a, .seg-tabs .seg, .site-title, .task-filters select'), function (el) {
      if (!el.offsetParent) return; var r = el.getBoundingClientRect();
      if (r.right > window.innerWidth + 1) fail('cortado à direita: ' + (el.getAttribute('aria-label') || el.textContent.trim() || el.className));
    });
    var title = document.querySelector('.site-title'); if (title && title.scrollWidth > title.clientWidth + 1) fail('nome do site cortado');
    var overlap = document.querySelector('.site-title'), tabs = document.querySelector('.seg-tabs');
    if (overlap && tabs) { var a = overlap.getBoundingClientRect(), b = tabs.getBoundingClientRect(); if (a.right > b.left && a.bottom > b.top && a.top < b.bottom) fail('abas por cima do nome do site'); }
    var task = document.querySelector('.task-title'); if (task && task.getBoundingClientRect().width < 120) fail('título da tarefa com ' + Math.round(task.getBoundingClientRect().width) + ' px');
    var small = {}; Array.prototype.forEach.call(document.querySelectorAll('.icon-btn, .seg, .nav-group-head, .tree-twisty, .link-btn, .ce-tab-close'), function (el) {
      if (!el.offsetParent) return; var r = el.getBoundingClientRect(); var pad = getComputedStyle(el);
      if (r.width && (r.height < 26 || r.width < 24)) small[el.className.split(' ')[0]] = Math.round(r.width) + 'x' + Math.round(r.height); });
    if (Object.keys(small).length) fail('alvos pequenos: ' + JSON.stringify(small));
    // under 1000 px, with no choice saved, the sidebar starts as a rail of icons and the width goes to the screen
    var side = document.querySelector('.sidebar').getBoundingClientRect().width;
    if (window.innerWidth < 1000) {
      if (!document.getElementById('app').classList.contains('is-rail') || side > 49) fail('barra lateral não recolheu: ' + Math.round(side) + ' px');
      if (view.width < window.innerWidth - 50) fail('sobrou ' + Math.round(view.width) + ' px para a tela');
      var code = document.querySelector('.ce-main'); if (code && code.offsetParent && code.getBoundingClientRect().width < 480) fail('visor da tela Código com ' + Math.round(code.getBoundingClientRect().width) + ' px');
      Array.prototype.forEach.call(document.querySelectorAll('#nav .nav-item, .rail-btn, #side-collapse'), function (el) {
        if (!el.title) fail('ícone do trilho sem dica'); if (el.getBoundingClientRect().right > side + 1) fail('ícone fora do trilho'); });
      Array.prototype.forEach.call(document.querySelectorAll('.rail-btn'), function (el) { if (el.getBoundingClientRect().bottom > window.innerHeight) fail('ícone de seção abaixo da janela'); });
      var sites = document.querySelector('[data-rail=section-sites]');
      if (sites) { sites.click(); var pop = document.querySelector('.side-section.is-pop'); var r = pop ? pop.getBoundingClientRect() : null;
        if (!r || r.top < 0 || r.bottom > window.innerHeight || r.left < side) fail('menu da seção fora da janela');
        if (document.scrollingElement.scrollTop) fail('abrir o menu rolou a página');
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        if (document.querySelector('.side-section.is-pop')) fail('Esc não fechou o menu'); }
    } else if (document.getElementById('app').classList.contains('is-rail')) fail('barra recolhida sem ninguém pedir');
    window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1);
  }, 2600);
})();
