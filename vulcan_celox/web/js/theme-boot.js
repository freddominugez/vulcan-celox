// Runs before the styles, so the app does not flash the wrong theme on open. The preference is kept here as a copy; the one in charge is
// the server (js/theme.mjs). Without localStorage, it follows the system.
(function () {
  var pref = "sistema";
  try { pref = localStorage.getItem("vulcan-theme") || "sistema"; } catch (_) { /* no storage */ }
  var dark = pref === "escuro" || (pref !== "claro" && window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "escuro" : "claro";
})();
