// Visão geral: sites em tabela densa, tarefas abertas, terminais ativos, sessões recentes e o índice geral.

import { brandLogo } from "../brand.mjs";
import { get, isMac, post } from "../api.mjs";
import { esc, formatDue, icon, progressBar, reportError, shortPath, todayISO } from "../dom.mjs";
import { t } from "../i18n.mjs";
import { terminals } from "../terminals.mjs";

export class OverviewView {
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.tasks = [];
    this.recent = [];
    this.nodeProjects = [];
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.unsubscribe = terminals.subscribe(() => {
      this.render();
      this.loadSessions();
    });
    this.render();
    this.loadTasks();
    this.loadSessions();
    this.loadNode();
  }

  async loadNode() {
    try {
      this.nodeProjects = (await get("/api/node-projects")).projects;
      if (this.nodeProjects.length) this.render();
    } catch {
      /* painel secundário */
    }
  }

  async loadSessions() {
    try {
      const data = await get("/api/sessions?site=*");
      this.recent = data.closed.slice(0, 8);
      this.render();
    } catch (err) {
      reportError(err);
    }
  }

  async loadTasks() {
    try {
      const data = await get("/api/tasks?site=*&status=todo,doing&sort=due");
      this.tasks = data.tasks;
      this.render();
    } catch (err) {
      reportError(err);
    }
  }

  update(state) {
    this.options.state = state;
    this.render();
  }

  render() {
    const { state } = this.options;
    const running = state.status.running;

    const siteProgress = state.progress.sites || {};
    const siteRows = state.sites.map((s) => {
      const p = siteProgress[s.name];
      const open = terminals.list(s.name).length;
      return `
        <tr data-site="${esc(s.name)}" class="row-link">
          <td><span class="dot ${s.exists ? (running ? "dot-ok" : "dot-idle") : "dot-err"}"></span><span class="strong">${esc(s.name)}</span></td>
          <td class="mono">${esc(s.domain)}</td>
          <td class="mono">${esc(s.php || "")}</td>
          <td>${s.secured ? `<span class="badge badge-ok">${icon("lock")}HTTPS</span>` : `<span class="dim">HTTP</span>`}</td>
          <td class="col-progress">${p ? `${progressBar(p)}<span class="num dim">${p.done}/${p.total}</span>` : `<span class="dim">${t("sem tarefas")}</span>`}</td>
          <td class="num">${open ? `${icon("terminal")}${open}` : ""}</td>
          <td class="col-actions">
            <button class="icon-btn" data-action="terminal" data-site="${esc(s.name)}" title="${t("Novo terminal em {site}", { site: esc(s.name) })}" aria-label="${t("Novo terminal")}">${icon("terminal")}</button>
            <button class="icon-btn" data-action="open" data-url="${esc(s.url)}" title="${t("Abrir {domain}", { domain: esc(s.domain) })}" aria-label="${t("Abrir site")}">${icon("globe")}</button>
          </td>
        </tr>`;
    }).join("");

    const today = todayISO();
    const taskRows = this.tasks.slice(0, 12).map((task) => `
      <li class="mini-task" data-site="${esc(task.site)}" data-tab="tasks">
        <span class="task-status-icon status-${esc(task.status)}">${icon(task.status === "doing" ? "circle-half" : "circle")}</span>
        <span class="mini-title">${esc(task.title)}</span>
        <span class="mini-site">${esc(task.site || t("Global"))}</span>
        ${task.due ? `<span class="task-due ${task.due < today ? "is-late" : ""}">${esc(formatDue(task.due))}</span>` : ""}
      </li>`).join("");

    const sessions = terminals.list();
    const termRows = sessions.map((s) => `
      <li class="mini-term" data-term="${s.info.id}" data-site="${esc(s.info.site || "")}">
        ${icon("terminal")}<span class="mini-title">${esc(s.info.title)}</span>
        <span class="mono dim">${esc(shortPath(s.info.cwd))}</span>
      </li>`).join("");

    const recentRows = this.recent.map((r) => `
      <li class="mini-term" data-session="${r.id}" data-site="${esc(r.site || "")}" title="${t("Ver a memória da sessão")}">
        ${icon("clock")}<span class="mini-title">${esc(r.title)}</span>
        <span class="mini-site">${esc(r.site || t("Global"))}</span>
        <span class="num dim">${t("{n} cmd", { n: r.commands })}${r.tasks.total ? ` · ${r.tasks.done}/${r.tasks.total}` : ""}</span>
      </li>`).join("");

    this.root.innerHTML = `
      <div class="page overview">
        ${brandLogo()}
        <div class="overview-grid">
          <div class="overview-main">
          <section class="panel">
            <header class="panel-head"><h2>Sites</h2><span class="count">${state.sites.length}</span>
              <div class="spacer"></div>
              ${state.backend.dashboard ? `<button class="btn btn-ghost btn-sm" data-action="dashboard">${icon("gauge")}<span>${t("Painel do Lerd")}</span></button>` : ""}
            </header>
            ${state.sites.length ? `
            <table class="table table-sites">
              <thead><tr><th>Site</th><th>${t("Domínio")}</th><th>PHP</th><th>TLS</th><th>${t("Tarefas")}</th><th class="num">${t("Terminais")}</th><th></th></tr></thead>
              <tbody>${siteRows}</tbody>
            </table>` : `
            <div class="empty-block">
              <h3>${t("Nenhum site registrado")}</h3>
              ${state.backend.name === "local" ? `<p>${t("Use o + em Sites PHP, na barra lateral, para adicionar uma pasta.")}</p>` : `<p>${t("Registre um projeto no {backend} para ele aparecer aqui.", { backend: esc(state.backend.label) })}</p>
              <code class="code-line">cd ~/Lerd/meu-projeto &amp;&amp; lerd link</code>`}
            </div>`}
          </section>

          ${this.nodeProjects.length ? `<section class="panel">
            <header class="panel-head"><h2>${t("Projetos Node")}</h2><span class="count">${this.nodeProjects.length}</span>
              <div class="spacer"></div><button class="btn btn-ghost btn-sm" data-go="#/node">${icon("hex")}<span>${t("Todos")}</span></button></header>
            <table class="table np-table"><thead><tr><th>${t("Projeto")}</th><th>Framework</th><th class="num">${t("Porta")}</th><th>${t("Serviços")}</th></tr></thead>
              <tbody>${this.nodeProjects.map((p) => `<tr class="np-row" data-go="#/node/${encodeURIComponent(p.name)}"><td><span class="np-mark">${icon("hex")}</span><b>${esc(p.name)}</b></td>
                <td>${esc(p.framework || "Node")}</td><td class="num">${p.porta || ""}</td>
                <td>${p.supabase ? `<span class="badge">Supabase</span>` : ""}${p.vercel ? `<span class="badge">Vercel</span>` : ""}</td></tr>`).join("")}</tbody></table>
          </section>` : ""}
          </div>
          <div class="overview-side">
            <section class="panel">
              <header class="panel-head"><h2>${t("Tarefas abertas")}</h2><span class="count">${this.tasks.length}</span>
                <div class="spacer"></div><button class="btn btn-ghost btn-sm" data-action="go-tasks">${t("Ver todas")}</button></header>
              ${this.tasks.length ? `<ul class="mini-list">${taskRows}</ul>` :
                `<div class="empty-inline">${icon("check-square")}<span>${t("Nada em aberto.")}</span></div>`}
            </section>
            <section class="panel">
              <header class="panel-head"><h2>${t("Terminais")}</h2><span class="count">${sessions.length}</span>
                <div class="spacer"></div><button class="btn btn-ghost btn-sm" data-action="new-terminal">${icon("plus")}<span>${t("Novo")}</span></button></header>
              ${sessions.length ? `<ul class="mini-list">${termRows}</ul>` :
                `<div class="empty-inline">${icon("terminal")}<span>${t("Nenhum terminal aberto. Abra um pelo site ou com {shortcut}.", { shortcut: isMac ? "⌘T" : "Ctrl+Shift+T" })}</span></div>`}
            </section>
            <section class="panel">
              <header class="panel-head"><h2>${t("Sessões recentes")}</h2><span class="count">${this.recent.length}</span>
                <div class="spacer"></div><button class="btn btn-ghost btn-sm" data-action="general-index" title="${t("Abrir INDICE.md com todas as sessões, tarefas e post-its")}">${icon("book")}<span>${t("Índice geral")}</span></button></header>
              ${this.recent.length ? `<ul class="mini-list">${recentRows}</ul>` :
                `<div class="empty-inline">${icon("clock")}<span>${t("Ao fechar um terminal, a memória dele em Markdown aparece aqui.")}</span></div>`}
            </section>
          </div>
        </div>
      </div>`;
  }

  async onClick(event) {
    const action = event.target.closest("[data-action]");
    try {
      if (action) {
        event.stopPropagation();
        const a = action.dataset.action;
        if (a === "terminal") {
          this.options.navigate(`#/sites/${encodeURIComponent(action.dataset.site)}/terminal`);
          this.options.command("newTerminal");
        }
        if (a === "open") await post("/api/open", { kind: "url", target: action.dataset.url });
        if (a === "dashboard") await post("/api/open", { kind: "dashboard" });
        if (a === "go-tasks") this.options.navigate("#/tasks");
        if (a === "new-terminal") this.options.command("newTerminal");
        if (a === "general-index") {
          const index = await get("/api/index/general");
          await post("/api/open", { kind: "file", target: index.path });
        }
        return;
      }
    } catch (err) {
      reportError(err);
      return;
    }
    const session = event.target.closest("[data-session]");
    if (session) {
      const site = session.dataset.site;
      this.options.navigate(site ? `#/sites/${encodeURIComponent(site)}/terminal/${session.dataset.session}` : `#/terminals/terminal/${session.dataset.session}`);
      return;
    }
    const term = event.target.closest("[data-term]");
    if (term) {
      this.options.navigate(term.dataset.site ? `#/sites/${encodeURIComponent(term.dataset.site)}/terminal/${term.dataset.term}` : `#/terminals/terminal/${term.dataset.term}`);
      return;
    }
    const row = event.target.closest("[data-site]");
    if (row && row.dataset.site) {
      this.options.navigate(`#/sites/${encodeURIComponent(row.dataset.site)}/${row.dataset.tab || "terminal"}`);
    } else if (row) {
      this.options.navigate("#/tasks");
    }
  }

  destroy() {
    this.unsubscribe();
  }
}
