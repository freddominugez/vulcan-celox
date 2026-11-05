// What the sidebar shows, chosen in Settings. The server holds the choice; the copy here avoids a flash on opening.

import { patch } from "./api.mjs";

const KEY = "vulcan-sidebar-hidden";
let hidden = new Set();

function remember(ids) {
  hidden = new Set(Array.isArray(ids) ? ids : []);
  try { localStorage.setItem(KEY, JSON.stringify([...hidden])); } catch (_) { /* applies only to this window */ }
  window.dispatchEvent(new CustomEvent("vulcan-sidebar"));
}

export const isHidden = (id) => hidden.has(id);

export async function setHidden(ids) {
  remember((await patch("/api/preferences", { sidebar_hidden: ids })).sidebar_hidden);
}

export function startSidebarPrefs() {
  try { hidden = new Set(JSON.parse(localStorage.getItem(KEY) || "[]")); } catch (_) { /* no storage */ }
  patch("/api/preferences", {}).then((prefs) => remember(prefs.sidebar_hidden)).catch(() => {});
}
