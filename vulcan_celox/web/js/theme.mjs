// Interface theme: System (default), Light or Dark. The terminal area keeps each tab's own theme in both.

import { patch } from "./api.mjs";
import { t } from "./i18n.mjs";

export const THEME_OPTIONS = [["sistema", t("Sistema")], ["claro", t("Claro")], ["escuro", t("Escuro")]];
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
  try { localStorage.setItem(KEY, pref); } catch (_) { /* applies only to this window */ }
  apply();
}

export async function setThemePref(value) {
  remember((await patch("/api/preferences", { theme: value })).theme);
}

export function startTheme() {
  try { pref = localStorage.getItem(KEY) || "sistema"; } catch (_) { /* no storage */ }
  if (media) media.addEventListener("change", () => { if (pref === "sistema") apply(); });
  patch("/api/preferences", {}).then((prefs) => remember(prefs.theme)).catch(() => {});
}
