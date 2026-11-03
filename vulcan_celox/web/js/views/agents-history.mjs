// Histórico de agentes: Claude Code e Codex juntos, busca por conteúdo, resultados agrupados por dia.

import { get } from "../api.mjs";
import { debounce, esc, icon, reportError } from "../dom.mjs";
import { AGENT_NAMES, agentMark, clock, RevisionWatch } from "../agents-ui.mjs";

const KINDS = [
  { id: "", label: "Tudo" }, { id: "pedidos", label: "Pedidos" }, { id: "respostas", label: "Respostas" },
  { id: "comandos", label: "Comandos" }, { id: "arquivos", label: "Arquivos" },
];
const AGENTS = [{ id: "", label: "Os dois agentes" }, { id: "claude", label: "Claude Code" }, { id: "codex", label: "Codex" }];
const KIND_LABEL = { user: "pedido", assistant: "resposta", command: "comando", file: "arquivo" };

function dayLabel(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Sem data";
  const today = new Date();
  const start = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((start(today) - start(d)) / 86400000);
  if (diff === 0) return "Hoje";
  if (diff === 1) return "Ontem";
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}${d.getFullYear() === today.getFullYear() ? "" : `/${d.getFullYear()}`}`;
}

/** O servidor marca o trecho achado com \x02 e \x03: escapa o texto e só então vira <mark>. */
function marked(text) {
  return esc(text).replace(/\x02/g, "<mark>").replace(/\x03/g, "</mark>");
}

export class AgentsHistoryView {
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.q = "";
    this.kind = "";
    this.agent = "";
    this.root.innerHTML = `
      <div class="page ag-page">
        <label class="ag-search">${icon("search")}
          <input id="ag-q" placeholder="Buscar em pedidos, respostas, comandos e arquivos" autocomplete="off" spellcheck="false" aria-label="Buscar no histórico de agentes">
          <span class="dim hint" data-role="count"></span></label>
        <div class="ag-bar-row">
          <div class="segmented" role="tablist" aria-label="Tipo">${KINDS.map((k) => `<button type="button" class="seg ${k.id === this.kind ? "is-on" : ""}" data-kind="${k.id}">${k.label}</button>`).join("")}</div>
          <div class="segmented" role="tablist" aria-label="Agente">${AGENTS.map((a) => `<button type="button" class="seg ${a.id === this.agent ? "is-on" : ""}" data-agent="${a.id}">${a.label}</button>`).join("")}</div>
        </div>
        <div data-role="hits"></div>
        <div data-role="note"></div>
      </div>`;
    this.input = this.root.querySelector("#ag-q");
    this.search = debounce(() => this.load(), 220);
    this.input.addEventListener("input", () => {
      this.q = this.input.value;
      this.search();
    });
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.watch = new RevisionWatch(() => this.load());
    this.load();
    setTimeout(() => this.input.focus(), 0);
  }

  async load() {
    const params = new URLSearchParams({ limit: "200" });
    if (this.q.trim()) params.set("q", this.q.trim());
    if (this.kind) params.set("kind", this.kind);
    if (this.agent) params.set("agent", this.agent);
    const seq = (this.seq = (this.seq || 0) + 1);
    try {
      const data = await get(`/api/agents/history?${params}`);
      if (seq !== this.seq || this.destroyed) return;  // resposta de uma busca mais antiga
      this.watch.seen(data.revision);
      this.render(data);
    } catch (err) {
      reportError(err);
    }
  }

  render(data) {
    const hits = data.hits;
    this.root.querySelector("[data-role=count]").textContent = this.q.trim() ? `${hits.length}${hits.length === 200 ? "+" : ""} resultados` : "";
    const groups = [];
    for (const h of hits) {
      const label = dayLabel(h.at);
      const last = groups[groups.length - 1];
      if (last && last.label === label) last.hits.push(h);
      else groups.push({ label, hits: [h] });
    }
    this.root.querySelector("[data-role=hits]").innerHTML = groups.length ? groups.map((g) => `
      <section class="ag-day"><h3>${esc(g.label)} <span class="count">${g.hits.length}</span></h3>
        <div class="panel">${g.hits.map((h) => `
          <button type="button" class="ag-hit" data-open="${esc(h.session_id)}">
            <span class="ag-time">${esc(clock(h.at))}</span>
            <span class="ag-hit-main"><span class="ag-hit-text ${h.kind === "command" || h.kind === "file" ? "mono" : ""}">${marked(h.text)}</span>
              <span class="ag-hit-src">${agentMark(h.agent)}<span>${esc(h.project || "sem projeto")}</span>${h.branch ? `<span class="mono">${esc(h.branch)}</span>` : ""}<span>${KIND_LABEL[h.kind] || h.kind}</span></span></span>
            ${icon("chevron-right")}
          </button>`).join("")}</div></section>`).join("")
      : `<div class="empty-inline">${icon("info")}<span>${this.q.trim() ? `Nada encontrado para “${esc(this.q.trim())}”. Tente outra palavra ou limpe os filtros.` : "Nenhum evento no histórico ainda."}</span></div>`;
    const cleanup = data.claude_cleanup;
    this.root.querySelector("[data-role=note]").innerHTML = `
      <div class="ag-note">${icon("info")}<div><b>Sessões antigas</b>
        <p>O ${AGENT_NAMES.claude} apaga sessões com mais de ${cleanup.days} dias (<code>cleanupPeriodDays</code> em <code>~/.claude/settings.json</code>${cleanup.configured ? "" : ", valor padrão"}).
          O Vulcan Celox guarda o resumo e o texto pesquisável dessas sessões no próprio índice, sem alterar a configuração do Claude.${data.fts ? "" : " Este SQLite não tem FTS5: a busca não ignora acentos."}</p></div></div>`;
  }

  onClick(event) {
    const open = event.target.closest("[data-open]");
    if (open) return this.options.navigate(`#/agentes/${encodeURIComponent(open.dataset.open)}`);
    const kind = event.target.closest("[data-kind]");
    const agent = event.target.closest("[data-agent]");
    if (kind) this.kind = kind.dataset.kind;
    if (agent) this.agent = agent.dataset.agent;
    if (kind || agent) {
      const btn = kind || agent;
      btn.parentElement.querySelectorAll(".seg").forEach((b) => b.classList.toggle("is-on", b === btn));
      this.load();
    }
    return null;
  }

  destroy() {
    this.destroyed = true;
    this.watch.stop();
  }
}
