// Sidebar collapsed to a rail of icons, to leave width in a small window. The choice goes to the preferences, next to
// the hidden items; while nothing was chosen, a window under 1000 px starts collapsed. On the rail, Sessions, Sites and
// Node become one icon each, and the icon opens that list in a menu next to the rail.

import { patch } from "./api.mjs";
import { $, icon } from "./dom.mjs";
import { t } from "./i18n.mjs";
import { isHidden } from "./sidebar-prefs.mjs";

const KEY = "vulcan-sidebar-collapsed";
const NARROW = 1000;
const SECTIONS = [
  { id: "section-sessions", el: "#side-sessions", icon: "history", label: () => t("Sessões") },
  { id: "section-sites", el: "#side-sites", icon: "globe", label: () => t("Sites") },
  { id: "section-node", el: "#side-node", icon: "hex", label: () => t("Projetos Node") },
];

let chosen = null;  // true or false once the user chose; null while the width decides

export const isRail = () => document.getElementById("app").classList.contains("is-rail");

function apply() {
  const rail = chosen === null ? window.innerWidth < NARROW : chosen;
  const app = document.getElementById("app");
  if (app.classList.contains("is-rail") === rail) return;
  app.classList.toggle("is-rail", rail);
  closeMenu();
  paintButton();
  window.dispatchEvent(new CustomEvent("vulcan-sidebar"));
}

function paintButton() {
  const button = $("#side-collapse");
  if (!button) return;
  const rail = isRail();
  const label = rail ? t("Expandir a barra lateral (⌘B)") : t("Recolher a barra lateral (⌘B)");
  button.title = label;
  button.setAttribute("aria-label", label);
  button.setAttribute("aria-expanded", String(!rail));
  button.innerHTML = icon(rail ? "chevron-right" : "chevron-left");
}

/** The section icons of the rail; a hidden section has none. */
export function renderRailSections() {
  const box = $("#rail-sections");
  if (!box) return;
  box.innerHTML = SECTIONS.filter((s) => !isHidden(s.id)).map((s) => `<button type="button" class="icon-btn rail-btn" data-rail="${s.id}"
    title="${s.label()}" aria-label="${s.label()}" aria-haspopup="true" aria-expanded="false">${icon(s.icon)}</button>`).join("");
}

function closeMenu() {
  document.querySelectorAll(".side-section.is-pop").forEach((el) => { el.classList.remove("is-pop"); el.style.top = ""; });
  document.querySelectorAll("[data-rail][aria-expanded=true]").forEach((b) => b.setAttribute("aria-expanded", "false"));
}

function openMenu(button) {
  const section = SECTIONS.find((s) => s.id === button.dataset.rail);
  const el = section && $(section.el);
  if (!el) return;
  const wasOpen = el.classList.contains("is-pop");
  closeMenu();
  if (wasOpen) return;
  el.classList.add("is-pop");
  // next to its icon, but always whole inside the window
  const top = Math.min(button.getBoundingClientRect().top, window.innerHeight - el.offsetHeight - 8);
  el.style.top = `${Math.max(8, top)}px`;
  button.setAttribute("aria-expanded", "true");
  const first = el.querySelector("a, button, input");
  if (first) first.focus({ preventScroll: true });
}

export async function toggleRail() {
  chosen = !isRail();
  try { localStorage.setItem(KEY, JSON.stringify(chosen)); } catch (_) { /* applies only to this window */ }
  apply();
  try {
    await patch("/api/preferences", { sidebar_collapsed: chosen });
  } catch (_) { /* the server keeps the old choice; this window keeps the new one */ }
}

export function startRail() {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || "null");
    chosen = typeof saved === "boolean" ? saved : null;
  } catch (_) { chosen = null; }
  apply();
  paintButton();
  renderRailSections();
  patch("/api/preferences", {}).then((prefs) => {
    chosen = typeof prefs.sidebar_collapsed === "boolean" ? prefs.sidebar_collapsed : null;
    try { localStorage.setItem(KEY, JSON.stringify(chosen)); } catch (_) { /* no storage */ }
    apply();
  }).catch(() => {});
  window.addEventListener("resize", () => { if (chosen === null) apply(); });
  window.addEventListener("vulcan-sidebar", renderRailSections);
  $("#side-collapse").addEventListener("click", () => toggleRail());
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-rail]");
    if (button) {
      openMenu(button);
      return;
    }
    // a link chosen in the menu closes it; a click elsewhere too
    if (!event.target.closest(".side-section.is-pop") || event.target.closest(".side-section.is-pop a")) closeMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && document.querySelector(".side-section.is-pop")) closeMenu();
  });
}
