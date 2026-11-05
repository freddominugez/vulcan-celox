// Sidebar; split out of app.mjs.

import { attentionCount } from "./attention-state.mjs";
import { NAV_GROUPS, SIDE_SECTIONS, app, lerdUnavailable, navById } from "./app-state.mjs";
import { $, esc, icon } from "./dom.mjs";
import { t } from "./i18n.mjs";
import { isHidden } from "./sidebar-prefs.mjs";
import { isRail } from "./sidebar-rail.mjs";
import { terminals } from "./terminals.mjs";

window.addEventListener("vulcan-attention", () => {
  const badge = document.querySelector("[data-attention-count]");
  if (!badge || Number(badge.dataset.attentionCount) !== attentionCount()) renderSidebar();
});
window.addEventListener("vulcan-sidebar", () => renderSidebar());

// while the environment comes up it is not "stopped": no alarm color for a start that is still going
const envStarting = (state) => Boolean(state.autostart && ["starting", "checking"].includes(state.autostart.phase));

export function renderSidebar() {
  const state = app.state;
  const counts = {
    terminals: terminals.list().length,
    agentes: attentionCount(),
    tasks: state ? state.progress.overall.total - state.progress.overall.done : 0,
  };
  const navItem = (n) => {
    const active = (n.routes || [n.id]).includes(app.route.name);
    const count = counts[n.id];
    let label = n.label;
    let dot = "";
    if (n.id === "ambiente" && state) {
      label = state.backend.available ? state.backend.label : "Lerd";
      const run = state.status.running;
      const up = envStarting(state);
      const word = run ? t("rodando") : up ? t("iniciando…") : state.backend.available ? t("parado") : t("ausente");
      dot = `<span class="nav-dot dot ${run ? "dot-ok" : state.backend.available && !up ? "dot-err" : "dot-idle"}" title="${word}" aria-label="${word}"></span>`;
    }
    return `<a class="nav-item ${active ? "is-on" : ""}" href="${n.hash}" title="${esc(isRail() ? label : n.desc || "")}" ${active ? 'aria-current="page"' : ""}>
      ${icon(n.icon)}<span>${esc(label)}</span>${count ? `<span class="count"${n.id === "agentes" ? ` data-attention-count="${count}" aria-label="${t("{n} aguardando você", { n: count })}"` : ""}>${count}</span>` : ""}${dot}</a>`;
  };
  // the redraw replaces the #nav elements; remember what had focus (group or link) to restore it
  const nav = $("#nav");
  const had = nav.contains(document.activeElement) ? document.activeElement : null;
  const refocus = had && (had.dataset.navGroup ? `[data-nav-group="${CSS.escape(had.dataset.navGroup)}"]`
    : had.getAttribute("href") ? `.nav-item[href="${CSS.escape(had.getAttribute("href"))}"]` : null);
  nav.innerHTML = NAV_GROUPS.map((g) => {
    const items = g.items.map((id) => navById[id]).filter((n) => !isHidden(n.id) && !(n.id === "ambiente" && lerdUnavailable()));
    if (!items.length) return "";
    const closed = Boolean(g.label && !isRail() && app.tree && app.tree.isOpen(`nav:${g.id}-closed`));  // the rail shows every icon
    // collapsed, the group still shows the current screen's item
    const shown = closed ? items.filter((n) => (n.routes || [n.id]).includes(app.route.name)) : items;
    return `<div class="nav-group ${closed ? "is-collapsed" : ""}" data-group="${g.id}">
      ${g.label ? `<button type="button" class="nav-group-head" data-nav-group="${g.id}" aria-expanded="${!closed}">
        ${icon("chevron-right", "side-chevron")}<span>${esc(g.label)}</span></button>` : ""}
      ${shown.map(navItem).join("")}</div>`;
  }).join("");
  if (refocus) {
    const again = nav.querySelector(refocus);
    if (again) again.focus();
  }
  SIDE_SECTIONS.forEach((section) => { $(section.el).hidden = isHidden(section.id); });

  if (app.tree) app.tree.render();
  if (!state) return;
  const running = state.status.running;
  // favorites on top and the rest in alphabetical order (same rule as core/site_list.py)
  const filter = app.siteFilter.trim().toLowerCase();
  const favorites = new Set(state.favorites || []);
  const sites = state.sites.filter((s) => !filter || s.name.toLowerCase().includes(filter) || s.domain.toLowerCase().includes(filter))
    .sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));
  const fav = sites.filter((s) => favorites.has(s.name));
  const rest = sites.filter((s) => !favorites.has(s.name));
  const progress = state.progress.sites || {};
  const siteHtml = (s) => {
    const active = app.route.name === "site" && app.route.site === s.name;
    const p = progress[s.name];
    const open = terminals.list(s.name).length;
    const tone = !s.exists ? "dot-err" : running ? "dot-ok" : "dot-idle";
    return `<a class="site-item ${active ? "is-on" : ""}" href="#/sites/${encodeURIComponent(s.name)}/terminal"
        title="${esc(s.domain)}" ${active ? 'aria-current="page"' : ""}>
      <span class="dot ${tone}"></span>
      <span class="site-name">${esc(s.domain.split(".")[0])}<span class="site-tld">.${esc(s.domain.split(".").slice(1).join("."))}</span></span>
      ${open ? `<span class="site-term" title="${t("{n} terminal(is) aberto(s)", { n: open })}">${icon("terminal")}${open}</span>` : ""}
      ${p && p.total ? `<span class="site-count" title="${esc(p.label)}">${p.done}/${p.total}</span>` : ""}
    </a>`;
  };
  $("#site-list").innerHTML = sites.length
    ? (fav.length ? `<div class="site-group">${icon("star", "i-sm")}${t("Favoritos")}</div>${fav.map(siteHtml).join("")}`
      + (rest.length ? `<div class="site-group">${t("Sites")}</div>` : "") : "") + rest.map(siteHtml).join("")
    : `<div class="side-empty">${state.sites.length ? t("Nenhum site com esse nome.") : state.backend.name === "local" ? t("Nenhum site. Use o + acima para adicionar uma pasta.") : t("Nenhum site. Rode <code>lerd link</code> numa pasta de projeto.")}</div>`;

  const nodeHtml = (p) => {
    const active = app.route.name === "node-projeto" && app.route.project === p.name;
    return `<a class="site-item ${active ? "is-on" : ""}" href="#/node/${encodeURIComponent(p.name)}" title="${esc(p.path)}" ${active ? 'aria-current="page"' : ""}>
      <span class="dot ${p.estado === "ok" ? "dot-node" : "dot-err"}"></span>
      <span class="site-name">${esc(p.name)}</span>${p.framework ? `<span class="site-tld node-fw">${esc(p.framework)}</span>` : ""}</a>`;
  };
  $("#node-list").innerHTML = app.nodeProjects.length ? app.nodeProjects.map(nodeHtml).join("")
    : `<div class="side-empty">${t("Nenhum projeto. Use + para adicionar a pasta de um app Next.js, Vite ou outro Node.")}</div>`;
}
