// What appears below the tabs: terminals side by side, the memory of a closed session, or the site tab.

import { get, isMac } from "./api.mjs";
import { $, esc, icon, reportError, shortPath } from "./dom.mjs";
import { t } from "./i18n.mjs";
import { renderMarkdown } from "./markdown.mjs";
import { terminals } from "./terminal-pool.mjs";
import { formatStamp } from "./terminal-tabs.mjs";
import { DebugView } from "./views/debug.mjs";
import { LogsView } from "./views/logs.mjs";
import { HarnessView } from "./views/harness.mjs";
import { NotesView } from "./views/notes.mjs";
import { SessionTagsView } from "./views/session-tags.mjs";
import { TasksView } from "./views/tasks.mjs";

const QUICK = [
  { label: "git status", command: "git status -sb" },
  { label: "composer install", command: "composer install", when: (s) => s && s.has_composer },
  { label: "php artisan about", command: "php artisan about", when: (s) => s && s.has_artisan },
  { label: "npm run dev", command: "npm run dev", when: (s) => s && s.has_package_json },
];

export function destroyChild(ws) {
  if (ws.child && ws.child.destroy) ws.child.destroy();
  ws.child = null;
  ws.childKey = "";
}

export function renderContent(ws) {
  const id = ws.activeId;
  const live = ws.isLive(id);
  const record = ws.records.get(id);
  if (ws.mode === "terminal") {
    destroyChild(ws);
    ws.resizeObserver.disconnect();
    if (live) return renderPanes(ws);
    if (id && record) return renderMemory(ws, record);
    if (id && !record) {
      ws.body.innerHTML = `<div class="loading"><span class="skeleton w-40"></span><span class="skeleton w-70"></span></div>`;
      return null;
    }
    ws.body.innerHTML = emptyHtml(ws);
    return null;
  }
  const key = `${ws.mode}:${id || "-"}:${ws.focus || ""}`;
  if (key === ws.childKey && ws.child) return null;
  destroyChild(ws);
  ws.resizeObserver.disconnect();
  // new container per tab: listeners from the previous tab must not duplicate actions (sticky note created twice)
  ws.body.innerHTML = "";
  const host = document.createElement("div");
  host.className = "ws-child";
  ws.body.appendChild(host);
  const onChange = () => {
    ws.loadSoon();
    if (ws.options.onDataChange) ws.options.onDataChange();
  };
  const title = live ? terminals.get(id).info.title : record ? record.title : "";
  const common = { site: ws.activeSite() || null, terminal: id, sessionTitle: title, sites: ws.options.sites || [], onChange, focus: ws.focus };
  if (ws.mode === "tasks") ws.child = new TasksView(host, common);
  if (ws.mode === "debug" && ws.options.site) ws.child = new DebugView(host, { site: ws.options.site });
  if (ws.mode === "harness" && ws.options.site) ws.child = new HarnessView(host, { site: ws.options.site });
  if (ws.mode === "logs" && ws.options.site) {  // site only
    ws.child = new LogsView(host, { site: ws.options.site, onTerminal: async (tabId) => {
      await terminals.sync();
      // the router switches the site section and selects the tab without remounting the screen
      location.hash = `#/sites/${encodeURIComponent(ws.options.site.name)}/terminal/${tabId}`;
    } });
  }
  if (ws.mode === "notes") ws.child = new NotesView(host, common);
  if (ws.mode === "tags") {
    if (id) ws.child = new SessionTagsView(host, { ...common, sessionId: id });
    else ws.body.innerHTML = emptyHtml(ws, t("As tags pertencem a uma sessão de terminal. Abra um terminal para começar."));
  }
  ws.childKey = key;
  return null;
}

function renderPanes(ws) {
  ws.body.innerHTML = `<div class="panes ${ws.splitId ? "is-split" : ""}"></div>`;
  const panes = $(".panes", ws.body);
  const order = ws.tabIds();
  const shownIds = [ws.activeId, ws.splitId].filter(Boolean).sort((a, b) => order.indexOf(a) - order.indexOf(b));
  for (const id of shownIds) {
    const session = terminals.get(id);
    const pane = document.createElement("div");
    pane.className = `pane ${ws.splitId && id === ws.activeId ? "is-focused" : ""}${session && session.info.theme ? ` has-theme t-${session.info.theme}` : ""}`;
    pane.dataset.session = id;
    pane.addEventListener("mousedown", () => ws.focusPane(id), true);
    panes.appendChild(pane);
    if (!session) continue;
    if (terminals.popped.has(id)) {
      pane.innerHTML = `
        <div class="term-empty is-compact"><div class="term-empty-inner">
          ${icon("external", "i-lg")}
          <h3>${t("{title} está numa janela própria", { title: esc(session.info.title) })}</h3>
          <p>${t("A sessão continua a mesma; feche a janela para trazê-la de volta.")}</p>
          <button class="btn" data-action="focus-popout" data-id="${id}">${t("Mostrar janela")}</button>
        </div></div>`;
    } else {
      session.mount(pane);
      ws.resizeObserver.observe(pane);
    }
  }
}

async function renderMemory(ws, record) {
  const id = record.id;
  const view = record.has_doc ? ws.memoryView : "memory";
  ws.body.innerHTML = `
    <div class="memory">
      <div class="memory-bar">
        ${icon("clock")}
        <span class="memory-title">${esc(record.title)}</span>
        <span class="dim">${t("encerrada {when}", { when: esc(formatStamp(record.closed_at)) })} · ${record.commands === 1 ? t("1 comando") : t("{n} comandos", { n: record.commands })}</span>
        ${record.has_doc ? `<div class="segmented" role="tablist" aria-label="${t("Conteúdo")}">
          <button class="seg ${view === "memory" ? "is-on" : ""}" data-action="memory-view" data-view="memory" role="tab" aria-selected="${view === "memory"}">${t("Memória")}</button>
          <button class="seg ${view === "doc" ? "is-on" : ""}" data-action="memory-view" data-view="doc" role="tab" aria-selected="${view === "doc"}">${icon("book")}<span>${t("Documentação")}</span></button>
        </div>` : ""}
        <div class="spacer"></div>
        ${record.memory_file ? `<button class="btn btn-ghost btn-sm" data-action="open-memory" data-id="${id}" data-file="${view}">${icon("external")}<span>${t("Abrir arquivo")}</span></button>` : ""}
        <button class="btn btn-ghost btn-sm" data-action="document" data-id="${id}">${icon("book")}<span>${record.has_doc ? t("Refazer documentação") : t("Documentar com IA")}</span></button>
        <button class="btn btn-sm" data-action="new">${icon("plus")}<span>${t("Novo terminal")}</span></button>
      </div>
      <article class="memory-doc md"><div class="loading"><span class="skeleton w-40"></span><span class="skeleton w-70"></span></div></article>
    </div>`;
  try {
    const data = view === "doc" ? await get(`/api/sessions/${id}/doc`) : await get(`/api/sessions/${id}`);
    if (ws.activeId !== id || ws.mode !== "terminal") return;
    const doc = $(".memory-doc", ws.body);
    const text = view === "doc" ? data.markdown : data.memory;
    if (doc) doc.innerHTML = text ? renderMarkdown(text) : `<p class="dim">${t("A memória desta sessão ainda não foi gravada.")}</p>`;
  } catch (err) {
    reportError(err);
  }
}

function emptyHtml(ws, message) {
  const site = ws.options.site;
  // on a site, the project commands (the first 6); elsewhere, the generic ones
  const list = ws.options.scope === "site" && ws.project.commands ? ws.project.commands.slice(0, 6)
    : QUICK.filter((q) => !q.when || q.when(site));
  const quick = list
    .map((q) => `<button class="chip-btn" data-action="quick" data-command="${esc(q.command)}" data-label="${esc(q.label)}">
        ${icon("play")}<span>${esc(q.label)}</span></button>`)
    .join("");
  const where = site ? shortPath(site.path) : "~";
  return `
    <div class="term-empty">
      <div class="term-empty-inner">
        <div class="term-empty-prompt"><span class="prompt-path">${esc(where)}</span> <span class="prompt-caret"></span></div>
        <h3>${site ? t("Nenhum terminal aberto em {site}", { site: esc(site.name) }) : t("Nenhum terminal aberto")}</h3>
        <p>${esc(message || t("Cada terminal é uma sessão: as tarefas, post-its e tags que você criar nela viram a memória em Markdown quando ele for fechado."))}</p>
        <div class="term-empty-actions">
          <button class="btn btn-primary" data-action="new">${icon("plus")}<span>${t("Novo terminal")}</span><kbd>${isMac ? "⌘T" : "Ctrl+⇧+T"}</kbd></button>
          ${quick}
        </div>
      </div>
    </div>`;
}
