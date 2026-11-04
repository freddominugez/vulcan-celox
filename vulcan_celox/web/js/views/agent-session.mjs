// Agent session: identity strip, loop alert and Resumo, Arquivos, Comandos and Linha do tempo tabs.

import { dismissSession } from "../attention-state.mjs";
import { every, get, post } from "../api.mjs";
import { terminals } from "../terminals.mjs";
import { esc, icon, reportError, shortPath, toast } from "../dom.mjs";
import { currentLanguage, t } from "../i18n.mjs";
import { CodeView } from "./code/code-view.mjs";
import { renderTurns, stepTurn } from "./agent-turns.mjs";
import { loadPr, prHtml } from "../pr-status.mjs";
import { AGENT_NAMES, agentMark, clock, copy, keepScroll, loopPrompt, relPath, relTime, RevisionWatch, splitPath, tokens, track } from "../agents-ui.mjs";

const TABS = [
  { id: "resumo", label: t("Resumo") },
  { id: "codigo", label: t("Código") },
  { id: "arquivos", label: t("Arquivos") },
  { id: "comandos", label: t("Comandos") },
  { id: "linha", label: t("Linha do tempo") },
];
const FILE_KINDS = { edit: "edit", new: t("novo"), read: t("leu"), delete: t("apagou") };
const CMD_KINDS = { shell: "shell", test: t("teste"), publish: t("publica") };
const PAGE = 200;

/** Estimated session cost at API price; a subscription bills differently. */
function costText(cost) {
  if (!cost || !cost.turns) return "";
  if (cost.value === null) return ` · ${t("custo sem preço conferido")}`;
  const v = cost.value >= 1 ? cost.value.toFixed(2) : cost.value.toFixed(3);
  return ` · ${cost.partial ? "≥ " : ""}US$ ${currentLanguage() === "pt" ? v.replace(".", ",") : v} ${t("estimado no preço da API")}`;
}

export class AgentSessionView {
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.id = options.id;
    this.tab = TABS.some((tb) => tb.id === options.tab) ? options.tab : "resumo";
    this.session = null;
    this.events = [];
    this.next = 0;
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.watch = new RevisionWatch(() => this.refresh());
    this.root.innerHTML = `<div class="loading"><span class="skeleton w-40"></span><span class="skeleton w-70"></span></div>`;
    this.load();
  }

  async load() {
    dismissSession(this.id);
    try {
      const data = await get(`/api/agents/sessions/${encodeURIComponent(this.id)}?limit=${PAGE}`);
      if (this.destroyed) return;  // left the screen during the read: do not start the clock
      this.session = data.session;
      this.events = data.events;
      this.next = data.next;
      this.watch.seen(data.revision);
      this.render();
      if (this.tab === "linha") this.loadTurns();
      this.loadDebug();
      if (!this.stopDebug) this.stopDebug = every(5000, () => { if (this.session && this.session.is_active) this.loadDebug(); });
    } catch (err) {
      if (this.destroyed) return;
      if (err.status === 404 && (this.retries = (this.retries || 0) + 1) <= 4) {
        this.retryTimer = setTimeout(() => this.load(), 1200);  // the index may still be on its first read
        return;
      }
      if (err.status === 404) {
        this.root.innerHTML = `<div class="page"><div class="empty-block"><h3>${t("Sessão de agente não encontrada")}</h3>
          <p>${t("Ela pode ter sido reindexada. Volte para a lista de agentes.")}</p><button class="btn" data-go="#/agentes">${t("Agentes")}</button></div></div>`;
        return;
      }
      reportError(err);
    }
  }

  /** Automatic update: swaps the summary and appends only the new events, without losing pagination. */
  async refresh() {
    if (!this.session) return this.load();
    const complete = this.next === null;
    // with all pages loaded, asks for what came after; otherwise only the summary (position past the end)
    const from = complete ? this.events.length : 1000000000;
    try {
      const data = await get(`/api/agents/sessions/${encodeURIComponent(this.id)}?from=${from}&limit=${PAGE}`);
      this.session = data.session;
      if (this.tab === "codigo") {
        // remounting the strip would drop the viewer's focus and selection; new events come in when switching tabs
        this.watch.seen(data.revision);
        if (complete) {
          this.events = this.events.concat(data.events);
          this.next = data.next === null ? null : this.events.length;
        }
        if (this.code) this.code.update(data.session);
        return;
      }
      if (complete) {
        this.events = this.events.concat(data.events);
        this.next = data.next === null ? null : this.events.length;
      }
      this.watch.seen(data.revision);
      keepScroll(this.root, () => this.render());
      if (this.tab === "linha") this.loadTurns(this.turns ? Math.max(50, this.turns.turns.length) : 50);
      this.loadDebug();
    } catch (err) {
      reportError(err);
    }
  }

  render() {
    const s = this.session;
    const theme = s.theme || "neutro";
    const counts = { arquivos: s.files.length, comandos: s.commands };
    const facts = [
      [t("Projeto"), esc(s.project || t("sem projeto"))], ["Branch", s.branch ? `<span class="mono">${esc(s.branch)}</span>` : t("não informado")],
      [t("Pasta"), `<span class="mono">${esc(shortPath(s.cwd))}</span>`], [t("Modelo"), esc(s.model || t("não informado"))],
      [null, s.turns === 1 ? t("1 pedido") : t("{n} pedidos", { n: s.turns })], [null, tokens(s.tokens) ? `${t("{n} tokens", { n: tokens(s.tokens) })}${costText(s.cost)}` : ""],
      [null, t("início {start}, última atividade {last}", { start: esc(relTime(s.started_at)), last: esc(relTime(s.last_activity_at)) })],
    ].filter((f) => f[1]);
    this.root.innerHTML = `
      <div class="page ag-page t-${esc(theme)} ${this.tab === "codigo" ? "is-code" : ""}">
        <div><button class="btn btn-ghost btn-sm" data-go="#/agentes">${icon("chevron-left")}<span>${t("Agentes")}</span></button></div>
        <section class="ag-banner">
          <div class="ag-eyebrow">${agentMark(s.agent)}<span>${esc(AGENT_NAMES[s.agent] || s.agent)}${s.cli_version ? ` ${esc(s.cli_version)}` : ""}</span>
            ${s.is_active ? `<span class="ag-live">${t("ativa")}</span>` : ""}${s.worktree ? `<span>${t("worktree {name}", { name: esc(s.worktree) })}</span>` : ""}
            ${s.subagents ? `<span>${t("{n} sub-agentes", { n: s.subagents })}</span>` : ""}
            ${s.pairing_id ? `<span>${t("pareada com uma aba do terminal")}</span>` : ""}</div>
          <h2 title="${esc(s.title || s.ask || "")}">${esc(s.headline || t("Sessão sem pedido registrado"))}</h2>
          <div class="ag-facts">${facts.map(([k, v]) => `<span>${k ? `${k} <b>${v}</b>` : v}</span>`).join("")}</div>
          ${s.harness ? `<a class="ag-harness" href="#/sites/${encodeURIComponent(s.harness.site)}/harness">${icon("check-square")}<span>${t("Harness: {line}", { line: esc(s.harness.line) })}</span>${icon("chevron-right")}</a>` : ""}
          <div class="ag-actions">
            ${s.pairing_id && terminals.get(s.pairing_id)
              ? `<button class="btn btn-sm ag-primary" data-action="goto-tab">${icon("terminal")}<span>${t("Ir para a aba")}</span></button>`
              : `<button class="btn btn-sm ag-primary" data-action="resume" title="${t("Abre um terminal na pasta da sessão e digita {cmd}", { cmd: s.agent === "codex" ? "codex resume" : "claude --resume" })}">${icon("play")}<span>${t("Retomar numa aba")}</span></button>`}
            <button class="btn btn-sm" data-action="copy-id">${icon("copy")}<span>${t("Copiar ID")}</span></button>
            <button class="btn btn-sm" data-action="folder">${icon("folder")}<span>${t("Abrir pasta")}</span></button>
            <button class="btn btn-sm" data-action="task">${icon("check-square")}<span>${t("Criar tarefa")}</span></button>
          </div>
        </section>
        ${s.loop ? `<div class="ag-alert">${icon("alert")}<div><b>${t("Possível loop de testes")}</b>
          <p>${t("{command} rodou {count} vezes desde {since}, sem nenhum commit entre as execuções.", { command: `<code>${esc(s.loop.command)}</code>`, count: s.loop.count, since: esc(clock(s.loop.since)) })}</p>
          <button class="btn btn-primary btn-sm" data-action="loop">${icon("copy")}<span>${t("Copiar prompt de saída")}</span></button></div></div>` : ""}
        <div class="segmented seg-tabs" role="tablist" aria-label="${t("Seções da sessão de agente")}">
          ${TABS.map((tb) => `<button type="button" class="seg ${tb.id === this.tab ? "is-on" : ""}" data-tab="${tb.id}" role="tab" aria-selected="${tb.id === this.tab}">${tb.label}${counts[tb.id] !== undefined ? ` <span class="count">${counts[tb.id]}</span>` : ""}</button>`).join("")}
        </div>
        ${this.body()}
      </div>`;
    this.placeCode();
  }

  /** The viewer survives tab changes: the same element returns to the screen, with selection and scroll. */
  placeCode() {
    const slot = this.root.querySelector(".code-slot");
    if (!slot) return;
    if (this.code) this.code.update(this.session);
    else this.code = new CodeView(this.session, this.options.target);
    slot.appendChild(this.code.el);
    this.code.attached();
  }

  body() {
    const s = this.session;
    if (this.tab === "codigo") return `<div class="code-slot"></div>`;
    if (this.tab === "arquivos") return this.panel(t("Arquivos tocados"), this.files(s.files));
    if (this.tab === "comandos") return this.panel(s.commands > s.command_list.length ? t("Comandos executados (últimos {shown} de {total})", { shown: s.command_list.length, total: s.commands }) : t("Comandos executados"), this.commands());
    if (this.tab === "linha") return this.panel(t("Linha do tempo"), this.timeline());
    const edited = s.files.filter((f) => f.kind !== "read");
    return `<div class="ag-cols">
      ${this.panel(t("Arquivos editados"), edited.length ? this.files(edited.slice(0, 8)) + (edited.length > 8 ? `<button class="ag-more" data-tab="arquivos">${t("Ver todos os {n}", { n: s.files.length })}</button>` : "") : `<div class="empty-inline">${icon("info")}<span>${t("Nenhum arquivo editado.")}</span></div>`)}
      <div class="ag-stack">
        ${this.panel(t("Publicação"), `<div class="ag-pad">${track(s)}<p class="dim hint">${{ none: s.files_edited ? t("Há arquivos editados sem commit.") : t("Nada editado ainda."), committed: t("Commit feito, falta o push."), pushed: t("Push feito."), pr_open: t("PR aberto.") }[s.published]}</p>${this.prLine()}</div>`,
          s.unpublished ? `<span class="badge">${s.published === "none" ? t("sem commit") : t("sem push")}</span>` : s.files_edited ? `<span class="badge badge-ok">${t("publicado")}</span>` : "")}
        ${this.debugPanel()}
        ${this.panel(t("Primeiro pedido"), `<p class="ag-pad ag-first">${esc(s.ask || t("não registrado"))}</p>`)}
      </div>
    </div>`;
  }

  /** Source of the publish state; with the preference off it queries nothing. */
  prLine() {
    if (!this.pr || this.prFor !== this.session.last_activity_at) this.loadPrStatus();
    return this.pr ? prHtml(this.pr) : "";
  }

  async loadPrStatus() {
    this.prFor = this.session.last_activity_at;
    const data = await loadPr({ session: this.id });
    if (this.destroyed || JSON.stringify(data) === JSON.stringify(this.pr)) return;
    this.pr = data;
    if (this.tab === "resumo" && this.session) keepScroll(this.root, () => this.render());
  }

  /** Lerd site errors during the session (only appears when the session folder is a Lerd site). */
  async loadDebug() {
    try {
      const data = await get(`/api/debug/agent/${encodeURIComponent(this.id)}`);
      const changed = JSON.stringify(data) !== JSON.stringify(this.debug);
      this.debug = data;
      if (changed && !this.destroyed && this.tab === "resumo") keepScroll(this.root, () => this.render());
    } catch (err) {
      this.debug = null;  // debugging is extra: failing here does not disturb the session
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
      <div class="ag-pad"><button class="btn btn-sm" data-action="debug-copy">${icon("copy")}<span>${t("Copiar resumo para o agente")}</span></button>
        <button class="btn btn-ghost btn-sm" data-go="#/sites/${encodeURIComponent(d.site)}/debug">${t("Abrir Depuração do site")}</button></div>`
      : `<div class="empty-inline">${icon("info")}<span>${t("Nenhuma exceção nem log de erro em {site} durante a sessão.", { site: esc(d.site) })}</span></div>`;
    return this.panel(t("Depuração no período"), content, d.events.length ? `<span class="badge badge-err">${d.events.length}</span>` : "");
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
    if (!list.length) return `<div class="empty-inline">${icon("info")}<span>${t("Nenhum comando.")}</span></div>`;
    return `<ul class="ag-list">${list.map((c) => `<li><span class="ag-kind k-${esc(c.kind)}">${esc(CMD_KINDS[c.kind] || c.kind)}</span>
      <code class="ag-cmd" title="${esc(c.text)}">${esc(c.text)}</code>${c.exit_code ? `<span class="badge badge-err">${t("saída {code}", { code: c.exit_code })}</span>` : ""}
      <span class="ag-time">${esc(clock(c.at))}</span></li>`).join("")}</ul>`;
  }

  timeline() {
    if (!this.turns) return `<div class="loading"><span class="skeleton w-70"></span></div>`;
    return renderTurns(this.id, this.session.project_root || this.session.cwd, this.turns);
  }

  async loadTurns(limit = 50) {
    try {
      const data = await get(`/api/agents/sessions/${encodeURIComponent(this.id)}/turns?limit=${limit}`);
      if (this.destroyed) return;
      this.turns = data;
      if (this.tab === "linha") keepScroll(this.root, () => this.render());
    } catch (err) {
      reportError(err);
    }
  }

  /** ⌘⇧↑/↓ in the Linha do tempo. */
  stepTurn(direction) {
    return this.tab === "linha" && stepTurn(this.root, direction);
  }

  onClick(event) {
    const tab = event.target.closest("[data-tab]");
    if (tab) {
      this.tab = tab.dataset.tab;
      if (this.tab === "linha") this.loadTurns(this.turns ? this.turns.turns.length : 50);
      const base = `#/agentes/${encodeURIComponent(this.id)}`;
      this.options.navigate(this.tab === "codigo" ? `${base}/codigo` : base, { silent: true });
      this.render();
      return;
    }
    const action = event.target.closest("[data-action]");
    if (!action) return;
    const s = this.session;
    if (action.dataset.action === "copy-id") copy(s.id, t("ID da sessão copiado."));
    if (action.dataset.action === "debug-copy") copy(this.debug.summary, t("Resumo copiado. Cole no terminal do agente."));
    if (action.dataset.action === "loop") copy(loopPrompt(s), t("Prompt de saída copiado. Cole no terminal da sessão."));
    if (action.dataset.action === "more") this.loadTurns(this.turns.turns.length + 50);
    if (action.dataset.action === "folder") post("/api/open", { kind: "finder", target: s.cwd }).catch(reportError);
    if (action.dataset.action === "task") this.createTask();
    if (action.dataset.action === "goto-tab") this.options.navigate(`#/terminals/terminal/${encodeURIComponent(s.pairing_id)}`);
    if (action.dataset.action === "resume") this.resume(action);
  }

  /** Resumes the session in a new tab: the server opens the terminal and types the agent command. */
  async resume(button) {
    button.disabled = true;
    try {
      const info = await post(`/api/agents/sessions/${encodeURIComponent(this.session.id)}/resume`);
      await terminals.sync();
      toast(t("Retomando a sessão na aba {title}.", { title: info.title }), { kind: "ok" });
      this.options.navigate(`#/terminals/terminal/${encodeURIComponent(info.id)}`);
    } catch (err) {
      button.disabled = false;
      reportError(err);
    }
  }

  /** Task from the agent session: stays in the paired tab, and with it on the site and in the notebook. */
  createTask() {
    const s = this.session;
    const backdrop = document.createElement("div");
    backdrop.className = "dialog-backdrop";
    backdrop.innerHTML = `<form class="dialog" role="dialog" aria-modal="true" aria-labelledby="ag-task-title" autocomplete="off">
      <h2 id="ag-task-title">${t("Criar tarefa")}</h2>
      <label class="field-label" for="ag-task">${t("Título")}</label>
      <input id="ag-task" name="title" class="input" maxlength="200" required value="${esc(`${s.project}${s.branch ? ` · ${s.branch}` : ""}: `)}">
      <p class="dim hint">${s.pairing_id ? t("A tarefa fica na aba do terminal pareada com esta sessão.") : t("Sem aba pareada: a tarefa fica em Tarefas, fora de projeto.")}</p>
      <div class="dialog-actions"><button type="button" class="btn" data-cancel>${t("Cancelar")}</button>
        <button type="submit" class="btn btn-primary">${icon("plus")}<span>${t("Criar tarefa")}</span></button></div></form>`;
    const close = () => backdrop.remove();
    backdrop.addEventListener("click", (e) => { if (e.target === backdrop || e.target.closest("[data-cancel]")) close(); });
    backdrop.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
    backdrop.querySelector("form").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await post("/api/tasks", { title: e.target.title.value.trim(), terminal: s.pairing_id || null });
        close();
        toast(t("Tarefa criada."), { kind: "ok" });
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
    if (this.code) this.code.destroy();
  }
}
