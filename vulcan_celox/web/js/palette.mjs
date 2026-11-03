// Paleta de comandos.

import { api, get, isMac, patch, post } from "./api.mjs";
import { noticesEnabled, setNoticesEnabled } from "./attention-notify.mjs";
import { AGENT_NAV, HELP_NAV, NAV, app } from "./app-state.mjs";
import { navigate, runCommand, service, toggleAutostart } from "./app.mjs";
import { prEnabled, setPrEnabled } from "./pr-status.mjs";
import { setThemePref, THEME_OPTIONS, themePref } from "./theme.mjs";
import { $, debounce, esc, icon, reportError, shortPath } from "./dom.mjs";
import { loadHelp } from "./help-content.mjs";
import { currentLanguage, t } from "./i18n.mjs";

let helpSections = [];
loadHelp().then((d) => { helpSections = d.secoes; }).catch(() => {});

const setLanguage = (language) => (language === currentLanguage() ? null : patch("/api/preferences", { language }).then(() => location.reload()).catch(reportError));

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
      { kind: t("Ações"), title: t("Novo terminal"), hint: isMac ? "⌘T" : "Ctrl+⇧+T", icon: "terminal", run: () => runCommand("newTerminal") },
      { kind: t("Ações"), title: t("Mostrar ou esconder o painel de terminal"), hint: isMac ? "⌘J" : "Ctrl+⇧+J", icon: "terminal", run: () => runCommand("togglePanel") },
      { kind: t("Ações"), title: t("Abrir terminal em… (pasta, agente e tema)"), hint: isMac ? "⇧⌘T" : "", icon: "folder", run: () => runCommand("newTerminalOptions") },
      { kind: t("Ações"), title: t("Iniciar ambiente"), icon: "play", run: () => service("start") },
      { kind: t("Ações"), title: t("Parar ambiente"), icon: "stop", run: () => service("stop") },
      { kind: t("Ações"), title: app.state && app.state.autostart && app.state.autostart.enabled ? t("Iniciar ambiente junto com o app: desligar") : t("Iniciar ambiente junto com o app: ligar"), icon: "bolt", run: () => toggleAutostart() },
      { kind: t("Ações"), title: noticesEnabled() ? t("Aviso do sistema quando um agente espera: desligar") : t("Aviso do sistema quando um agente espera: ligar"), icon: "info", run: () => setNoticesEnabled(!noticesEnabled()).catch(reportError) },
      ...THEME_OPTIONS.map(([id, label]) => ({ kind: t("Tema"), title: themePref() === id ? t("Tema: {label} (em uso)", { label }) : t("Tema: {label}", { label }), icon: "circle-half", run: () => setThemePref(id).catch(reportError) })),
      { kind: t("Ações"), title: prEnabled() ? t("Estado do PR pelo GitHub (usa a rede): desligar") : t("Estado do PR pelo GitHub (usa a rede): ligar"), icon: "branch", run: () => setPrEnabled(!prEnabled()).catch(reportError) },
      { kind: t("Ações"), title: t("Abrir painel do Lerd"), icon: "gauge", run: () => post("/api/open", { kind: "dashboard" }).catch(reportError) },
      { kind: t("Ações"), title: t("Idioma: English"), icon: "help", run: () => setLanguage("en") },
      { kind: t("Ações"), title: t("Idioma: Português"), icon: "help", run: () => setLanguage("pt") },
      ...[...NAV, ...AGENT_NAV, ...HELP_NAV].map((n) => ({ kind: t("Ir para"), title: n.label, icon: n.icon, run: () => navigate(n.hash) })),
      ...helpSections.map((h) => ({ kind: t("Ajuda"), title: t("Ajuda: {titulo}", { titulo: h.titulo }), sub: h.resumo, icon: "help", run: () => navigate(`#/ajuda/${h.id}`) })),
    ];
    const sites = (app.state ? app.state.sites : []).flatMap((s) => [
      { kind: t("Sites"), title: s.name, sub: s.domain, icon: "globe", run: () => navigate(`#/sites/${encodeURIComponent(s.name)}/terminal`) },
      { kind: t("Sites"), title: t("Terminal em {name}", { name: s.name }), sub: shortPath(s.path), icon: "terminal", run: () => { navigate(`#/sites/${encodeURIComponent(s.name)}/terminal`); runCommand("newTerminal"); } },
    ]);
    return [...base, ...sites].filter((a) => !q || a.title.toLowerCase().includes(q) || (a.sub || "").toLowerCase().includes(q));
  },
  search: debounce(async function search(query) {
    let hits = [];
    if (query.trim().length > 1) {
      try {
        const data = await get(`/api/search?q=${encodeURIComponent(query)}`);
        hits = data.hits.filter((h) => h.kind !== "site").map((h) => ({
          kind: { task: t("Tarefas"), note: t("Post-its"), tag: t("Tags") }[h.kind] || h.kind,
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
    }).join("") : `<li class="pal-empty">${t("Nada encontrado.")}</li>`;
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
