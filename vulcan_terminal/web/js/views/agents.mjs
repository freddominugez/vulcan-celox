// Agentes: sessões do Claude Code e do Codex com KPIs, filtros e trilha de publicação.

import { get } from "../api.mjs";
import { esc, icon, reportError } from "../dom.mjs";
import { agentPill, emptyAgents, keepScroll, relTime, RevisionWatch, track } from "../agents-ui.mjs";

const FILTERS = [
  { id: "todas", label: "Todas", query: "" },
  { id: "ativas", label: "Ativas", query: "active=1" },
  { id: "claude", label: "Claude Code", query: "agent=claude" },
  { id: "codex", label: "Codex", query: "agent=codex" },
  { id: "sem", label: "Sem publicar", query: "unpublished=1" },
];

function remembered(key, fallback) {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}

function remember(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* sem armazenamento: só não lembra */
  }
}

export class AgentsView {
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.filter = remembered("vulcan-agents-filter", "todas");
    this.project = remembered("vulcan-agents-project", "");
    this.data = null;
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.root.addEventListener("change", (e) => this.onChange(e));
    this.watch = new RevisionWatch(() => this.load());
    this.root.innerHTML = `<div class="loading"><span class="skeleton w-40"></span><span class="skeleton w-70"></span></div>`;
    this.load();
  }

  query() {
    const parts = [FILTERS.find((f) => f.id === this.filter)?.query, this.project ? `project=${encodeURIComponent(this.project)}` : ""];
    return parts.filter(Boolean).join("&");
  }

  async load() {
    try {
      this.data = await get(`/api/agents/sessions?${this.query()}`);
      this.watch.seen(this.data.revision);
      keepScroll(this.root, () => this.render());
    } catch (err) {
      reportError(err);
    }
  }

  render() {
    const d = this.data;
    const k = d.kpis;
    const body = d.total === 0 ? emptyAgents(d.roots) : d.sessions.length
      ? `<div class="ag-cards">${d.sessions.map((s) => this.card(s)).join("")}</div>`
      : `<div class="empty-inline">${icon("info")}<span>Nenhuma sessão neste filtro.</span></div>`;
    this.root.innerHTML = `
      <div class="page ag-page">
        <div class="ag-kpis">
          <div class="ag-kpi"><span class="ag-kpi-v">${k.active}</span><span class="ag-kpi-l">ativas agora</span></div>
          <div class="ag-kpi"><span class="ag-kpi-v">${k.files_edited_today}</span><span class="ag-kpi-l">arquivos editados hoje</span></div>
          <div class="ag-kpi ${k.unpublished ? "is-warn" : ""}"><span class="ag-kpi-v">${k.unpublished}</span><span class="ag-kpi-l">sessões sem push</span></div>
          <div class="ag-kpi"><span class="ag-kpi-v">${k.tokens_today >= 1000 ? `${Math.round(k.tokens_today / 1000)} mil` : k.tokens_today}</span><span class="ag-kpi-l">tokens nas sessões de hoje</span></div>
        </div>
        <div class="ag-bar-row">
          <div class="segmented" role="tablist" aria-label="Filtro">
            ${FILTERS.map((f) => `<button type="button" class="seg ${f.id === this.filter ? "is-on" : ""}" data-filter="${f.id}" role="tab" aria-selected="${f.id === this.filter}">${f.label}</button>`).join("")}
          </div>
          <select class="select select-sm" data-role="project" aria-label="Projeto">
            <option value="">Todos os projetos</option>
            ${d.projects.map((p) => `<option value="${esc(p.name)}" ${p.name === this.project ? "selected" : ""}>${esc(p.name)} (${p.count})</option>`).join("")}
          </select>
          <span class="spacer"></span>
          <span class="dim hint">Lido de ~/.claude e ~/.codex, sem chave de API</span>
          <button class="btn btn-sm" data-go-usage>${icon("gauge")}<span>Uso e custo</span></button>
        </div>
        ${body}
      </div>`;
  }

  card(s) {
    const theme = s.theme || "neutro";
    const ask = s.headline || "Sessão sem pedido registrado";
    return `<button type="button" class="ag-card t-${esc(theme)}" data-open="${esc(s.id)}">
      <span class="ag-band"><span class="dot ${s.is_active ? "dot-ok" : ""}"></span><span class="ag-proj">${esc(s.project || "sem projeto")}</span>
        <span class="ag-when">${s.pairing_id ? "pareada · " : ""}${esc(relTime(s.last_activity_at))}</span></span>
      <span class="ag-body">
        <span class="ag-meta">${agentPill(s.agent)}${s.branch ? `<span class="ag-pill mono">${icon(s.worktree ? "tree" : "branch")}${esc(s.branch)}</span>` : ""}
          ${s.is_active ? `<span class="ag-pill is-ok">ativa</span>` : ""}${s.loop ? `<span class="ag-pill is-warn">${icon("alert")}possível loop</span>` : ""}</span>
        <span class="ag-ask">${esc(ask)}</span>
        <span class="ag-stats">${s.files_edited} editados · ${s.files_read} lidos · ${s.commands} comandos${s.subagents ? ` · ${s.subagents} sub-agentes` : ""}</span>
        ${track(s)}
      </span>
    </button>`;
  }

  onClick(event) {
    if (event.target.closest("[data-go-usage]")) return this.options.navigate("#/agentes/uso");
    const open = event.target.closest("[data-open]");
    if (open) return this.options.navigate(`#/agentes/${encodeURIComponent(open.dataset.open)}`);
    const filter = event.target.closest("[data-filter]");
    if (filter) {
      this.filter = filter.dataset.filter;
      remember("vulcan-agents-filter", this.filter);
      this.load();
    }
    return null;
  }

  onChange(event) {
    if (event.target.dataset.role === "project") {
      this.project = event.target.value;
      remember("vulcan-agents-project", this.project);
      this.load();
    }
  }

  destroy() {
    this.watch.stop();
  }
}
