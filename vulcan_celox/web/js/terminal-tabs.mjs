// Workspace tab bar: rendering, keyboard and rename on double-click.

import { isMac, isNative, patch } from "./api.mjs";
import { $$, esc, icon, reportError, shortPath } from "./dom.mjs";
import { t } from "./i18n.mjs";
import { syncTabs } from "./terminal-watch.mjs";
import { terminals } from "./terminal-pool.mjs";

export function formatStamp(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function renderTabs(ws) {
  const ids = ws.tabIds();
  const tabs = ids.map((id, i) => {
    const live = terminals.get(id);
    const record = ws.records.get(id);
    const title = live ? live.info.title : record ? record.title : id;
    const active = id === ws.activeId;
    const shown = id === ws.splitId;
    const popped = terminals.popped.has(id);
    const site = live ? live.info.site : record && record.site;
    const where = ws.options.scope === "all" && site ? `<span class="tab-site">${esc(site)}</span>` : "";
    const theme = (live && live.info.theme) || (record && record.theme) || null;
    const cls = [active && "is-active", shown && "is-shown", popped && "is-popped", !live && "is-closed",
      live && !live.alive && "is-dead", live && live.disconnected && "is-disconnected",
      theme && `has-theme t-${theme}`].filter(Boolean).join(" ");
    const tip = live ? shortPath(live.info.cwd) : t("Encerrada {when}", { when: formatStamp(record && record.closed_at) });
    const state = live && live.disconnected ? ` · ${t("desconectado: Enter no terminal reconecta")}` : "";
    return `<div class="tab ${cls}" role="tab" tabindex="${active ? 0 : -1}" aria-selected="${active}" data-action="select" data-id="${id}" title="${esc(tip + state)}">
        ${icon(!live ? "clock" : popped ? "external" : "terminal")}
        <span class="tab-label">${esc(title)}</span>${where}
        ${live && live.alive && live.info.long_running ? `<span class="tab-long" title="${t("Processo longo: {command}", { command: esc(live.info.command) })}">${t("longo")}</span>` : ""}
        ${live && i < 9 && !isNative ? `<kbd class="tab-kbd">${isMac ? "⌘" : "Ctrl+⇧+"}${i + 1}</kbd>` : ""}
        <button class="tab-close" data-action="close" data-id="${id}" aria-label="${live ? t("Fechar terminal") : t("Tirar da barra")}"
          title="${live ? t("Fechar terminal e salvar a memória") : t("Tirar da barra (a memória continua salva)")}">${icon("x")}</button>
      </div>`;
  }).join("");

  // the history of closed sessions lives in the sidebar (folder Histórico)

  const terminalTools = ws.mode === "terminal" && ws.isLive(ws.activeId) ? `
    <button class="icon-btn ${ws.splitId ? "is-on" : ""}" data-action="split" title="${t("Dividir")}" aria-label="${t("Dividir")}">${icon("split")}</button>
    <button class="icon-btn" data-action="find" title="${t("Buscar no terminal ({key})", { key: isMac ? "⌘F" : "Ctrl+⇧+F" })}" aria-label="${t("Buscar no terminal")}">${icon("search")}</button>
    <button class="icon-btn" data-action="copy-output" title="${t("Copiar a saída do terminal")}" aria-label="${t("Copiar a saída do terminal")}">${icon("copy")}</button>
    <button class="icon-btn" data-action="popout" title="${t("Destacar em janela (⇧⌘D)")}" aria-label="${t("Destacar em janela")}">${icon("external")}</button>
    <button class="icon-btn" data-action="document" data-id="${ws.activeId}" title="${t("Documentar esta sessão com IA")}" aria-label="${t("Documentar com IA")}">${icon("book")}</button>` : "";

  const viewing = ws.isHistory() ? ws.records.get(ws.activeId) : null;
  const historyChip = viewing ? `
    <div class="history-chip" title="${t("Sessão encerrada, aberta pela pasta Histórico")}">
      ${icon("clock")}<span>${t("Histórico · {title}", { title: esc(viewing.title) })}</span>
      <button class="tab-close" data-action="leave-history" aria-label="${t("Voltar aos terminais")}" title="${t("Voltar aos terminais")}">${icon("x")}</button>
    </div>` : "";
  ws.strip.innerHTML = `
    <div class="tabs">${tabs}</div>${historyChip}
    <button class="icon-btn" data-action="new" title="${t("Novo terminal ({key})", { key: isMac ? "⌘T" : "Ctrl+⇧+T" })}" aria-label="${t("Novo terminal")}">${icon("plus")}</button>
    <div class="tabstrip-spacer"></div>
    ${ws.options.scope === "site" && ws.project.commands ? `<button class="btn btn-sm cmd-btn" data-action="commands" aria-haspopup="menu" title="${t("Comandos do projeto")}">${icon("play")}<span>${t("Comandos")}</span></button>` : ""}
    ${ws.project.runtimeChip()}
    ${terminalTools}`;
  $$(".tab.is-active", ws.strip).forEach((t) => t.scrollIntoView({ block: "nearest", inline: "nearest" }));
  const activeLive = ws.mode === "terminal" ? terminals.get(ws.activeId) : null;
  ws.promptBar.update(activeLive ? activeLive.info.cwd : null, activeLive ? activeLive.info.id : null);
  if (ws.options.onChange) ws.options.onChange(ws.sessions().length);
  syncTabs();
}

/** Tabs by keyboard: arrows switch tabs, Enter or space opens the focused one. */
export function onTabKey(ws, event) {
  const tab = event.target.closest && event.target.closest(".tab[role=tab]");
  if (!tab || event.target.closest(".tab-close")) return;
  const tabs = [...tab.parentElement.querySelectorAll(".tab[role=tab]")];
  const i = tabs.indexOf(tab);
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    ws.select(tab.dataset.id);
  } else if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
    event.preventDefault();
    const next = tabs[(i + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length];
    ws.select(next.dataset.id);
    const again = ws.root.querySelector(`.tab[data-id="${next.dataset.id}"]`);
    if (again) again.focus();
  }
}

export function renameTabOnDblClick(ws, event) {
  const tab = event.target.closest(".tab[data-action='select']");
  if (!tab) return;
  const id = tab.dataset.id;
  const live = terminals.get(id);
  const record = ws.records.get(id);
  const label = tab.querySelector(".tab-label");
  if (!label || (!live && !record)) return;
  const input = document.createElement("input");
  input.className = "tab-rename";
  input.value = live ? live.info.title : record.title;
  label.replaceWith(input);
  input.focus();
  input.select();
  let done = false;
  const finish = async (save) => {
    if (done) return;
    done = true;
    const title = input.value.trim();
    if (save && title) {
      try {
        if (live) await terminals.rename(id, title);
        else await patch(`/api/sessions/${id}`, { title });
        await ws.loadSessions();
      } catch (err) {
        reportError(err);
      }
    }
    ws.renderTabs();
  };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") finish(true);
    if (e.key === "Escape") finish(false);
  });
  input.addEventListener("blur", () => finish(true));
}
