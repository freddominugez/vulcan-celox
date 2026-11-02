// Sessão de agente: faixa com a identidade, alerta de loop e abas Resumo, Arquivos, Comandos e Linha do tempo.

import { every, get, post } from "../api.mjs";
import { terminals } from "../terminals.mjs";
import { esc, icon, reportError, shortPath, toast } from "../dom.mjs";
import { AGENT_NAMES, agentMark, clock, copy, keepScroll, loopPrompt, relPath, relTime, RevisionWatch, splitPath, tokens, track } from "../agents-ui.mjs";

const TABS = [
  { id: "resumo", label: "Resumo" },
  { id: "arquivos", label: "Arquivos" },
  { id: "comandos", label: "Comandos" },
  { id: "linha", label: "Linha do tempo" },
];
const FILE_KINDS = { edit: "edit", new: "novo", read: "leu", delete: "apagou" };
const CMD_KINDS = { shell: "shell", test: "teste", publish: "publica" };
const EVENT_TEXT = { user: "Pedido", assistant: "Resposta", command: "Comando", file: "Arquivo" };
const PAGE = 200;

/** Custo estimado da sessão no preço da API (vt-22 C4); assinatura cobra de outro jeito. */
function costText(cost) {
  if (!cost || !cost.turns) return "";
  if (cost.value === null) return " · custo sem preço conferido";
  const v = cost.value >= 1 ? cost.value.toFixed(2) : cost.value.toFixed(3);
  return ` · ${cost.partial ? "≥ " : ""}US$ ${v.replace(".", ",")} estimado no preço da API`;
}

export class AgentSessionView {
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.id = options.id;
    this.tab = "resumo";
    this.session = null;
    this.events = [];
    this.next = 0;
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.watch = new RevisionWatch(() => this.refresh());
    this.root.innerHTML = `<div class="loading"><span class="skeleton w-40"></span><span class="skeleton w-70"></span></div>`;
    this.load();
  }

  async load() {
    try {
      const data = await get(`/api/agents/sessions/${encodeURIComponent(this.id)}?limit=${PAGE}`);
      if (this.destroyed) return;  // saiu da tela durante a leitura: não liga o relógio
      this.session = data.session;
      this.events = data.events;
      this.next = data.next;
      this.watch.seen(data.revision);
      this.render();
      this.loadDebug();
      if (!this.stopDebug) this.stopDebug = every(5000, () => { if (this.session && this.session.is_active) this.loadDebug(); });
    } catch (err) {
      if (this.destroyed) return;
      if (err.status === 404 && (this.retries = (this.retries || 0) + 1) <= 4) {
        this.retryTimer = setTimeout(() => this.load(), 1200);  // o índice pode ainda estar na primeira leitura
        return;
      }
      if (err.status === 404) {
        this.root.innerHTML = `<div class="page"><div class="empty-block"><h3>Sessão de agente não encontrada</h3>
          <p>Ela pode ter sido reindexada. Volte para a lista de agentes.</p><button class="btn" data-go="#/agentes">Agentes</button></div></div>`;
        return;
      }
      reportError(err);
    }
  }

  /** Atualização automática: troca o resumo e acrescenta só os eventos novos, sem perder a paginação. */
  async refresh() {
    if (!this.session) return this.load();
    const complete = this.next === null;
    // com todas as páginas carregadas, pede o que veio depois; senão só o resumo (posição além do fim)
    const from = complete ? this.events.length : 1000000000;
    try {
      const data = await get(`/api/agents/sessions/${encodeURIComponent(this.id)}?from=${from}&limit=${PAGE}`);
      this.session = data.session;
      if (complete) {
        this.events = this.events.concat(data.events);
        this.next = data.next === null ? null : this.events.length;
      }
      this.watch.seen(data.revision);
      keepScroll(this.root, () => this.render());
      this.loadDebug();
    } catch (err) {
      reportError(err);
    }
  }

  async more() {
    try {
      const data = await get(`/api/agents/sessions/${encodeURIComponent(this.id)}?from=${this.next}&limit=${PAGE}`);
      this.events = this.events.concat(data.events);
      this.next = data.next;
      keepScroll(this.root, () => this.render());
    } catch (err) {
      reportError(err);
    }
  }

  render() {
    const s = this.session;
    const theme = s.theme || "neutro";
    const counts = { arquivos: s.files.length, comandos: s.commands };
    const facts = [
      ["Projeto", esc(s.project || "sem projeto")], ["Branch", s.branch ? `<span class="mono">${esc(s.branch)}</span>` : "não informado"],
      ["Pasta", `<span class="mono">${esc(shortPath(s.cwd))}</span>`], ["Modelo", esc(s.model || "não informado")],
      [null, `${s.turns} ${s.turns === 1 ? "pedido" : "pedidos"}`], [null, tokens(s.tokens) ? `${tokens(s.tokens)} tokens${costText(s.cost)}` : ""],
      [null, `início ${esc(relTime(s.started_at))}, última atividade ${esc(relTime(s.last_activity_at))}`],
    ].filter((f) => f[1]);
    this.root.innerHTML = `
      <div class="page ag-page t-${esc(theme)}">
        <div><button class="btn btn-ghost btn-sm" data-go="#/agentes">${icon("chevron-left")}<span>Agentes</span></button></div>
        <section class="ag-banner">
          <div class="ag-eyebrow">${agentMark(s.agent)}<span>${esc(AGENT_NAMES[s.agent] || s.agent)}${s.cli_version ? ` ${esc(s.cli_version)}` : ""}</span>
            ${s.is_active ? `<span class="ag-live">ativa</span>` : ""}${s.worktree ? `<span>worktree ${esc(s.worktree)}</span>` : ""}
            ${s.subagents ? `<span>${s.subagents} sub-agentes</span>` : ""}
            ${s.pairing_id ? `<span>pareada com uma aba do terminal</span>` : ""}</div>
          <h2 title="${esc(s.title || s.ask || "")}">${esc(s.headline || "Sessão sem pedido registrado")}</h2>
          <div class="ag-facts">${facts.map(([k, v]) => `<span>${k ? `${k} <b>${v}</b>` : v}</span>`).join("")}</div>
          ${s.harness ? `<a class="ag-harness" href="#/sites/${encodeURIComponent(s.harness.site)}/harness">${icon("check-square")}<span>Harness: ${esc(s.harness.line)}</span>${icon("chevron-right")}</a>` : ""}
          <div class="ag-actions">
            ${s.pairing_id && terminals.get(s.pairing_id)
              ? `<button class="btn btn-sm ag-primary" data-action="goto-tab">${icon("terminal")}<span>Ir para a aba</span></button>`
              : `<button class="btn btn-sm ag-primary" data-action="resume" title="Abre um terminal na pasta da sessão e digita ${s.agent === "codex" ? "codex resume" : "claude --resume"}">${icon("play")}<span>Retomar numa aba</span></button>`}
            <button class="btn btn-sm" data-action="copy-id">${icon("copy")}<span>Copiar ID</span></button>
            <button class="btn btn-sm" data-action="folder">${icon("folder")}<span>Abrir pasta</span></button>
            <button class="btn btn-sm" data-action="task">${icon("check-square")}<span>Criar tarefa</span></button>
          </div>
        </section>
        ${s.loop ? `<div class="ag-alert">${icon("alert")}<div><b>Possível loop de testes</b>
          <p><code>${esc(s.loop.command)}</code> rodou ${s.loop.count} vezes desde ${esc(clock(s.loop.since))}, sem nenhum commit entre as execuções.</p>
          <button class="btn btn-primary btn-sm" data-action="loop">${icon("copy")}<span>Copiar prompt de saída</span></button></div></div>` : ""}
        <div class="segmented seg-tabs" role="tablist" aria-label="Seções da sessão de agente">
          ${TABS.map((t) => `<button type="button" class="seg ${t.id === this.tab ? "is-on" : ""}" data-tab="${t.id}" role="tab" aria-selected="${t.id === this.tab}">${t.label}${counts[t.id] !== undefined ? ` <span class="count">${counts[t.id]}</span>` : ""}</button>`).join("")}
        </div>
        ${this.body()}
      </div>`;
  }

  body() {
    const s = this.session;
    if (this.tab === "arquivos") return this.panel("Arquivos tocados", this.files(s.files));
    if (this.tab === "comandos") return this.panel(`Comandos executados${s.commands > s.command_list.length ? ` (últimos ${s.command_list.length} de ${s.commands})` : ""}`, this.commands());
    if (this.tab === "linha") return this.panel("Linha do tempo", this.timeline());
    const edited = s.files.filter((f) => f.kind !== "read");
    return `<div class="ag-cols">
      ${this.panel("Arquivos editados", edited.length ? this.files(edited.slice(0, 8)) + (edited.length > 8 ? `<button class="ag-more" data-tab="arquivos">Ver todos os ${s.files.length}</button>` : "") : `<div class="empty-inline">${icon("info")}<span>Nenhum arquivo editado.</span></div>`)}
      <div class="ag-stack">
        ${this.panel("Publicação", `<div class="ag-pad">${track(s)}<p class="dim hint">${{ none: s.files_edited ? "Há arquivos editados sem commit." : "Nada editado ainda.", committed: "Commit feito, falta o push.", pushed: "Push feito.", pr_open: "PR aberto." }[s.published]}</p></div>`,
          s.unpublished ? `<span class="badge">${s.published === "none" ? "sem commit" : "sem push"}</span>` : s.files_edited ? `<span class="badge badge-ok">publicado</span>` : "")}
        ${this.debugPanel()}
        ${this.panel("Primeiro pedido", `<p class="ag-pad ag-first">${esc(s.ask || "não registrado")}</p>`)}
      </div>
    </div>`;
  }

  /** vt-06 C4: erros do site do Lerd durante a sessão (só aparece quando a pasta da sessão é um site do Lerd). */
  async loadDebug() {
    try {
      const data = await get(`/api/debug/agent/${encodeURIComponent(this.id)}`);
      const changed = JSON.stringify(data) !== JSON.stringify(this.debug);
      this.debug = data;
      if (changed && !this.destroyed && this.tab === "resumo") keepScroll(this.root, () => this.render());
    } catch (err) {
      this.debug = null;  // a depuração é extra: falha aqui não atrapalha a sessão
    }
  }

  debugPanel() {
    const d = this.debug;
    if (!d || !d.available || !d.site) return "";
    const list = d.events.slice(-8).reverse();
    const content = list.length ? `<ul class="ag-list">${list.map((e) => `<li class="log-${esc(e.tone || "err")}">
        <span class="ag-kind log-level">${esc((e.data.level || e.kind).toUpperCase())}</span>
        <span class="ag-path" title="${esc(e.file ? `${e.file}:${e.line}` : "")}">${esc(e.data.message || e.text || "")}</span>
        <span class="ag-time">${esc(clock(e.ts))}</span></li>`).join("")}</ul>
      <div class="ag-pad"><button class="btn btn-sm" data-action="debug-copy">${icon("copy")}<span>Copiar resumo para o agente</span></button>
        <button class="btn btn-ghost btn-sm" data-go="#/sites/${encodeURIComponent(d.site)}/debug">Abrir Depuração do site</button></div>`
      : `<div class="empty-inline">${icon("info")}<span>Nenhuma exceção nem log de erro em ${esc(d.site)} durante a sessão.</span></div>`;
    return this.panel("Depuração no período", content, d.events.length ? `<span class="badge badge-err">${d.events.length}</span>` : "");
  }

  panel(title, content, extra = "") {
    return `<section class="panel ag-panel"><div class="panel-head"><h2>${title}</h2><span class="spacer"></span>${extra}</div>${content}</section>`;
  }

  files(list) {
    const root = this.session.project_root || this.session.cwd;
    return `<ul class="ag-list">${list.map((f) => {
      const [dir, name] = splitPath(relPath(f.path, root));
      return `<li><span class="ag-kind k-${esc(f.kind)}">${esc(FILE_KINDS[f.kind] || f.kind)}</span><span class="ag-path" title="${esc(f.path)}"><span class="dim">${esc(dir)}</span>${esc(name)}</span><span class="ag-time">${esc(relTime(f.last_at))}</span></li>`;
    }).join("")}</ul>`;
  }

  commands() {
    const list = this.session.command_list.slice().reverse();
    if (!list.length) return `<div class="empty-inline">${icon("info")}<span>Nenhum comando.</span></div>`;
    return `<ul class="ag-list">${list.map((c) => `<li><span class="ag-kind k-${esc(c.kind)}">${esc(CMD_KINDS[c.kind] || c.kind)}</span>
      <code class="ag-cmd" title="${esc(c.text)}">${esc(c.text)}</code>${c.exit_code ? `<span class="badge badge-err">saída ${c.exit_code}</span>` : ""}
      <span class="ag-time">${esc(clock(c.at))}</span></li>`).join("")}</ul>`;
  }

  timeline() {
    if (!this.events.length) return `<div class="empty-inline">${icon("info")}<span>Nenhum evento.</span></div>`;
    const root = this.session.project_root || this.session.cwd;
    return `<ol class="ag-timeline">${this.events.map((e) => {
      const text = e.kind === "file" ? `${esc(FILE_KINDS[e.tool] || e.tool)} <code>${esc(relPath(e.text, root))}</code>`
        : e.kind === "command" ? `<code>${esc(e.text)}</code>` : esc(e.text.length > 400 ? `${e.text.slice(0, 399)}…` : e.text);
      return `<li class="ev-${esc(e.kind)}${e.tool === "publish" ? " ev-publish" : ""}"><span class="ag-time">${esc(clock(e.at))}</span><span class="ag-pt"></span>
        <span class="ag-ev"><b>${esc(EVENT_TEXT[e.kind] || e.kind)}</b> ${text}</span></li>`;
    }).join("")}</ol>${this.next !== null ? `<button class="ag-more" data-action="more">Carregar mais</button>` : ""}`;
  }

  onClick(event) {
    const tab = event.target.closest("[data-tab]");
    if (tab) {
      this.tab = tab.dataset.tab;
      this.render();
      return;
    }
    const action = event.target.closest("[data-action]");
    if (!action) return;
    const s = this.session;
    if (action.dataset.action === "copy-id") copy(s.id, "ID da sessão copiado.");
    if (action.dataset.action === "debug-copy") copy(this.debug.summary, "Resumo copiado. Cole no terminal do agente.");
    if (action.dataset.action === "loop") copy(loopPrompt(s), "Prompt de saída copiado. Cole no terminal da sessão.");
    if (action.dataset.action === "more") this.more();
    if (action.dataset.action === "folder") post("/api/open", { kind: "finder", target: s.cwd }).catch(reportError);
    if (action.dataset.action === "task") this.createTask();
    if (action.dataset.action === "goto-tab") this.options.navigate(`#/terminals/terminal/${encodeURIComponent(s.pairing_id)}`);
    if (action.dataset.action === "resume") this.resume(action);
  }

  /** Retoma a sessão numa aba nova (vt-19 C4): o servidor abre o terminal e digita o comando do agente. */
  async resume(button) {
    button.disabled = true;
    try {
      const info = await post(`/api/agents/sessions/${encodeURIComponent(this.session.id)}/resume`);
      await terminals.sync();
      toast(`Retomando a sessão na aba ${info.title}.`, { kind: "ok" });
      this.options.navigate(`#/terminals/terminal/${encodeURIComponent(info.id)}`);
    } catch (err) {
      button.disabled = false;
      reportError(err);
    }
  }

  /** Tarefa a partir da sessão de agente (vt-18 C5): fica na aba pareada, e com ela no site e no caderno. */
  createTask() {
    const s = this.session;
    const backdrop = document.createElement("div");
    backdrop.className = "dialog-backdrop";
    backdrop.innerHTML = `<form class="dialog" role="dialog" aria-modal="true" aria-labelledby="ag-task-title" autocomplete="off">
      <h2 id="ag-task-title">Criar tarefa</h2>
      <label class="field-label" for="ag-task">Título</label>
      <input id="ag-task" name="title" class="input" maxlength="200" required value="${esc(`${s.project}${s.branch ? ` · ${s.branch}` : ""}: `)}">
      <p class="dim hint">${s.pairing_id ? "A tarefa fica na aba do terminal pareada com esta sessão." : "Sem aba pareada: a tarefa fica em Tarefas, fora de projeto."}</p>
      <div class="dialog-actions"><button type="button" class="btn" data-cancel>Cancelar</button>
        <button type="submit" class="btn btn-primary">${icon("plus")}<span>Criar tarefa</span></button></div></form>`;
    const close = () => backdrop.remove();
    backdrop.addEventListener("click", (e) => { if (e.target === backdrop || e.target.closest("[data-cancel]")) close(); });
    backdrop.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
    backdrop.querySelector("form").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await post("/api/tasks", { title: e.target.title.value.trim(), terminal: s.pairing_id || null });
        close();
        toast("Tarefa criada.", { kind: "ok" });
      } catch (err) {
        reportError(err);
      }
    });
    document.body.appendChild(backdrop);
    const input = backdrop.querySelector("input");
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  }

  destroy() {
    this.destroyed = true;
    clearTimeout(this.retryTimer);
    this.watch.stop();
    if (this.stopDebug) this.stopDebug();
  }
}
