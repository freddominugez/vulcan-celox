// Branches e worktrees: o que ficou sem commit, sem push ou parado, cruzando as sessões com o git real.

import { api, every, post } from "../api.mjs";
import { esc, icon, reportError, shortPath } from "../dom.mjs";
import { agentMark, copy, keepScroll, relTime } from "../agents-ui.mjs";
import { loadPr, prEnabled, prHtml } from "../pr-status.mjs";

const REFRESH_MS = 30000;  // git é caro: a tela se atualiza a cada 30 s ou pelo botão Atualizar

const BAD = ["sem commit", "sem push", "sem upstream"];
const TONE = { "sem commit": "is-warn", "sem push": "is-warn", "sem upstream": "is-warn", "PR aberto": "is-ok", publicado: "is-ok" };

function conciliationPrompt(row, project) {
  return `Liste o que está sem commit e sem push no branch ${row.branch || "atual"} (${row.path}) do projeto ${project.project}. `
    + "Faça commit do que estiver pronto e push. "
    + (row.worktree ? `Depois do merge, me diga se a worktree ${row.worktree} pode ser removida; não remova sem me perguntar. ` : "")
    + "Não troque de branch nem crie worktree nova.";
}

export class AgentsBranchesView {
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.projects = [];
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.stopTimer = every(REFRESH_MS, () => this.load());
    this.root.innerHTML = `<div class="loading"><span class="skeleton w-40"></span><span class="skeleton w-70"></span></div>`;
    this.load();
  }

  async load(fresh = false) {
    if (this.loading) return;  // uma consulta por vez
    this.loading = true;
    try {
      const data = await api(`/api/agents/repos${fresh ? "?fresh=1" : ""}`, { timeout: 120000 });  // git em vários repositórios
      this.projects = data.projects;
      keepScroll(this.root, () => this.render());
      this.fillPr();
    } catch (err) {
      reportError(err);
    } finally {
      this.loading = false;
    }
  }

  /** Só com a preferência ligada: uma consulta por pasta, com cache de 60 s no servidor. */
  fillPr() {
    this.root.querySelectorAll("[data-pr-row]").forEach(async (slot) => {
      const data = await loadPr({ path: slot.dataset.prRow });
      if (slot.isConnected) slot.innerHTML = prHtml(data);
    });
  }

  render() {
    const pending = this.projects.reduce((n, p) => n + p.rows.filter((r) => BAD.includes(r.state)).length, 0);
    this.root.innerHTML = `
      <div class="page ag-page">
        <div class="ag-bar-row"><span class="dim hint">Sessões dos agentes cruzadas com <code>git status</code> e <code>git worktree list</code>, só leitura.
          ${pending ? `<b class="ag-warn-text">${pending} ${pending === 1 ? "branch precisa" : "branches precisam"} de atenção.</b>` : ""}</span>
          <span class="spacer"></span><button class="btn btn-sm" data-action="reload">${icon("restart")}<span>Atualizar</span></button></div>
        ${this.projects.length ? this.projects.map((p, pi) => `
          <section class="panel ag-panel">
            <div class="panel-head">${icon("folder")}<h2>${esc(p.project)}</h2><span class="dim hint mono">${esc(shortPath(p.root))}</span>
              <span class="spacer"></span>${p.is_repo ? `<span class="dim hint">aberto em <span class="mono">${esc(p.current_branch || "?")}</span></span>` : `<span class="badge">sem git</span>`}</div>
            ${p.rows.map((r, ri) => this.row(p, r, pi, ri)).join("")}
          </section>`).join("")
          : `<div class="empty-inline">${icon("info")}<span>Nenhuma sessão de agente ainda: os branches aparecem aqui quando houver sessões.</span></div>`}
      </div>`;
  }

  row(p, r, pi, ri) {
    const detail = [r.dirty ? `${r.dirty} ${r.dirty === 1 ? "arquivo alterado" : "arquivos alterados"}` : "",
      r.ahead ? `${r.ahead} ${r.ahead === 1 ? "commit" : "commits"} à frente` : ""].filter(Boolean).join(" · ");
    return `<div class="ag-br-row">
      <div class="ag-br-name">${icon(r.worktree ? "tree" : "branch")}<span class="mono">${esc(r.branch || "sem branch")}</span>
        ${r.worktree ? `<span class="ag-pill">worktree ${esc(r.worktree)}</span>` : ""}${r.orphan_worktree ? `<span class="ag-pill is-warn">sem sessão</span>` : ""}</div>
      <div class="ag-br-state">
        <span class="ag-pill ${TONE[r.state] || ""}">${esc(r.state)}</span>
        ${r.stale_days ? `<span class="ag-pill is-err">${icon("alert")}parada há ${r.stale_days} dias</span>` : ""}
        ${detail ? `<span class="dim hint">${esc(detail)}</span>` : ""}
        ${r.state === "PR aberto" && !prEnabled() ? `<span class="dim hint">pelos comandos da sessão</span>` : ""}
        ${prEnabled() && r.path ? `<span data-pr-row="${esc(r.path)}"></span>` : ""}
        ${r.sessions.map((s) => `<button type="button" class="ag-pill ag-pill-btn" data-open="${esc(s.id)}" title="Abrir sessão">${agentMark(s.agent)}${esc(relTime(s.last_activity_at))}</button>`).join("")}
      </div>
      <div class="ag-br-actions">
        ${BAD.includes(r.state) ? `<button class="btn btn-sm" data-copy="${pi}:${ri}">${icon("copy")}<span>Copiar prompt de conciliação</span></button>` : ""}
        <button class="icon-btn" data-folder="${esc(r.path)}" title="Abrir pasta" aria-label="Abrir pasta">${icon("folder")}</button>
      </div>
    </div>`;
  }

  onClick(event) {
    const open = event.target.closest("[data-open]");
    if (open) return this.options.navigate(`#/agentes/${encodeURIComponent(open.dataset.open)}`);
    const copyBtn = event.target.closest("[data-copy]");
    if (copyBtn) {
      const [pi, ri] = copyBtn.dataset.copy.split(":").map(Number);
      const project = this.projects[pi];
      copy(conciliationPrompt(project.rows[ri], project), "Prompt de conciliação copiado. Cole no terminal da sessão.");
    }
    const folder = event.target.closest("[data-folder]");
    if (folder) post("/api/open", { kind: "finder", target: folder.dataset.folder }).catch(reportError);
    if (event.target.closest("[data-action=reload]")) this.load(true);
    return null;
  }

  destroy() {
    this.stopTimer();
  }
}
