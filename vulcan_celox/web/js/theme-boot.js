// Roda antes dos estilos, para o app não piscar no tema errado ao abrir. A preferência fica aqui em cópia; quem manda é
// o servidor (js/theme.mjs). Sem localStorage, segue o sistema.
(function () {
  var pref = "sistema";
  try { pref = localStorage.getItem("vulcan-theme") || "sistema"; } catch (_) { /* sem armazenamento */ }
  var dark = pref === "escuro" || (pref !== "claro" && window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "escuro" : "claro";
})();
