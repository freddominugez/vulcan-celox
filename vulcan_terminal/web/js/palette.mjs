// Paleta de comandos.

import { api, get, isMac, post } from "./api.mjs";
import { noticesEnabled, setNoticesEnabled } from "./attention-notify.mjs";
import { AGENT_NAV, HELP_NAV, NAV, app } from "./app-state.mjs";
import { navigate, runCommand, service, toggleAutostart } from "./app.mjs";
import { prEnabled, setPrEnabled } from "./pr-status.mjs";
import { setThemePref, THEME_OPTIONS, themePref } from "./theme.mjs";
import { $, debounce, esc, icon, reportError, shortPath } from "./dom.mjs";
import { loadHelp } from "./help-content.mjs";

let helpSections = [];
loadHelp().then((d) => { helpSections = d.secoes; }).catch(() => {});

export const palette = {
  items: [],
  index: 0,
  open() {
    const el = $("#palette");
    el.hidden = false;
    const input = $("#palette-input");
    input.value = "";
    this.search("");
    input.focus();
  },
  close() {
    $("#palette").hidden = true;
  },
  actions(query) {
    const q = query.toLowerCase();
    const base = [
      { kind: "Ações", title: "Novo terminal", hint: isMac ? "⌘T" : "Ctrl+⇧+T", icon: "terminal", run: () => runCommand("newTerminal") },
      { kind: "Ações", title: "Mostrar ou esconder o painel de terminal", hint: isMac ? "⌘J" : "Ctrl+⇧+J", icon: "terminal", run: () => runCommand("togglePanel") },
      { kind: "Ações", title: "Abrir terminal em… (pasta, agente e tema)", hint: isMac ? "⇧⌘T" : "", icon: "folder", run: () => runCommand("newTerminalOptions") },
      { kind: "Ações", title: "Iniciar ambiente", icon: "play", run: () => service("start") },
      { kind: "Ações", title: "Parar ambiente", icon: "stop", run: () => service("stop") },
      { kind: "Ações", title: `Iniciar ambiente junto com o app: ${app.state && app.state.autostart && app.state.autostart.enabled ? "desligar" : "ligar"}`, icon: "bolt", run: () => toggleAutostart() },
      { kind: "Ações", title: `Aviso do sistema quando um agente espera: ${noticesEnabled() ? "desligar" : "ligar"}`, icon: "info", run: () => setNoticesEnabled(!noticesEnabled()).catch(reportError) },
      ...THEME_OPTIONS.map(([id, label]) => ({ kind: "Tema", title: `Tema: ${label}${themePref() === id ? " (em uso)" : ""}`, icon: "circle-half", run: () => setThemePref(id).catch(reportError) })),
      { kind: "Ações", title: `Estado do PR pelo GitHub (usa a rede): ${prEnabled() ? "desligar" : "ligar"}`, icon: "branch", run: () => setPrEnabled(!prEnabled()).catch(reportError) },
      { kind: "Ações", title: "Abrir painel do Lerd", icon: "gauge", run: () => post("/api/open", { kind: "dashboard" }).catch(reportError) },
      ...[...NAV, ...AGENT_NAV, ...HELP_NAV].map((n) => ({ kind: "Ir para", title: n.label, icon: n.icon, run: () => navigate(n.hash) })),
      ...helpSections.map((h) => ({ kind: "Ajuda", title: `Ajuda: ${h.titulo}`, sub: h.resumo, icon: "help", run: () => navigate(`#/ajuda/${h.id}`) })),
    ];
    const sites = (app.state ? app.state.sites : []).flatMap((s) => [
      { kind: "Sites", title: s.name, sub: s.domain, icon: "globe", run: () => navigate(`#/sites/${encodeURIComponent(s.name)}/terminal`) },
      { kind: "Sites", title: `Terminal em ${s.name}`, sub: shortPath(s.path), icon: "terminal", run: () => { navigate(`#/sites/${encodeURIComponent(s.name)}/terminal`); runCommand("newTerminal"); } },
    ]);
    return [...base, ...sites].filter((a) => !q || a.title.toLowerCase().includes(q) || (a.sub || "").toLowerCase().includes(q));
  },
  search: debounce(async function search(query) {
    let hits = [];
    if (query.trim().length > 1) {
      try {
        const data = await get(`/api/search?q=${encodeURIComponent(query)}`);
        hits = data.hits.filter((h) => h.kind !== "site").map((h) => ({
          kind: { task: "Tarefas", note: "Post-its", tag: "Tags" }[h.kind] || h.kind,
          title: h.title, sub: h.snippet, icon: { task: "check-square", note: "note", tag: "tag" }[h.kind],
          run: () => {
            if (h.kind === "tag") navigate("#/tags");
            else if (h.site) navigate(`#/sites/${encodeURIComponent(h.site)}/${h.kind === "task" ? "tasks" : "notes"}`);
            else navigate(h.kind === "task" ? "#/tasks" : "#/notes");
          },
        }));
      } catch {
        hits = [];
      }
    }
    palette.items = [...palette.actions(query), ...hits].slice(0, 40);
    palette.index = 0;
    palette.render();
  }, 90),
  render() {
    let lastKind = "";
    $("#palette-results").innerHTML = this.items.length ? this.items.map((item, i) => {
      const header = item.kind !== lastKind ? `<li class="pal-group">${esc(item.kind)}</li>` : "";
      lastKind = item.kind;
      return `${header}<li class="pal-item ${i === this.index ? "is-on" : ""}" data-index="${i}" role="option" aria-selected="${i === this.index}">
        ${icon(item.icon || "dot")}<span class="pal-title">${esc(item.title)}</span>
        ${item.sub ? `<span class="pal-sub">${esc(item.sub)}</span>` : ""}${item.hint ? `<kbd>${esc(item.hint)}</kbd>` : ""}</li>`;
    }).join("") : `<li class="pal-empty">Nada encontrado.</li>`;
    const on = $(".pal-item.is-on");
    if (on) on.scrollIntoView({ block: "nearest" });
  },
  run(index) {
    const item = this.items[index];
    if (!item) return;
    this.close();
    item.run();
  },
};
