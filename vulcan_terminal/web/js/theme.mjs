// Tema da interface: Sistema (padrão), Claro ou Escuro. A área do terminal mantém o tema de cada aba nos dois.

import { patch } from "./api.mjs";

export const THEME_OPTIONS = [["sistema", "Sistema"], ["claro", "Claro"], ["escuro", "Escuro"]];
const KEY = "vulcan-theme";
let pref = "sistema";
const media = window.matchMedia ? matchMedia("(prefers-color-scheme: dark)") : null;

export function themePref() {
  return pref;
}

function apply() {
  const dark = pref === "escuro" || (pref !== "claro" && media && media.matches);
  document.documentElement.dataset.theme = dark ? "escuro" : "claro";
  window.dispatchEvent(new CustomEvent("vulcan-theme"));
}

function remember(value) {
  pref = THEME_OPTIONS.some(([id]) => id === value) ? value : "sistema";
  try { localStorage.setItem(KEY, pref); } catch (_) { /* vale só nesta janela */ }
  apply();
}

export async function setThemePref(value) {
  remember((await patch("/api/preferences", { theme: value })).theme);
}

export function startTheme() {
  try { pref = localStorage.getItem(KEY) || "sistema"; } catch (_) { /* sem armazenamento */ }
  if (media) media.addEventListener("change", () => { if (pref === "sistema") apply(); });
  patch("/api/preferences", {}).then((prefs) => remember(prefs.theme)).catch(() => {});
}
