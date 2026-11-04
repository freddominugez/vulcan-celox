// Branches and worktrees: what is left uncommitted, unpushed or stalled, crossing the sessions with real git.

import { api, every, post } from "../api.mjs";
import { esc, icon, reportError, shortPath } from "../dom.mjs";
import { t } from "../i18n.mjs";
import { agentMark, copy, keepScroll, relTime } from "../agents-ui.mjs";
import { loadPr, prEnabled, prHtml } from "../pr-status.mjs";

const REFRESH_MS = 30000;  // git is expensive: the screen refreshes every 30 s or via the Atualizar button

const BAD = ["sem commit", "sem push", "sem upstream"];
const STATE_LABEL = { "sem commit": t("sem commit"), "sem push": t("sem push"), "sem upstream": t("sem upstream"), "PR aberto": t("PR aberto"), publicado: t("publicado"), "nada editado": t("nada editado"), "sem git": t("sem git") };
const TONE = { "sem commit": "is-warn", "sem push": "is-warn", "sem upstream": "is-warn", "PR aberto": "is-ok", publicado: "is-ok" };

function conciliationPrompt(row, project) {
  return [t("Liste o que está sem commit e sem push no branch {branch} ({path}) do projeto {project}.", { branch: row.branch || t("atual"), path: row.path, project: project.project }),
    t("Faça commit do que estiver pronto e push."),
    row.worktree ? t("Depois do merge, me diga se a worktree {name} pode ser removida; não remova sem me perguntar.", { name: row.worktree }) : "",
    t("Não troque de branch nem crie worktree nova.")].filter(Boolean).join(" ");
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
    if (this.loading) return;  // one query at a time
    this.loading = true;
    try {
      const data = await api(`/api/agents/repos${fresh ? "?fresh=1" : ""}`, { timeout: 120000 });  // git across several repositories
      this.projects = data.projects;
      keepScroll(this.root, () => this.render());
      this.fillPr();
    } catch (err) {
      reportError(err);
    } finally {
      this.loading = false;
    }
  }

  /** Only with the preference on: one query per folder, with a 60 s cache on the server. */
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
        <div class="ag-bar-row"><span class="dim hint">${t("Sessões dos agentes cruzadas com {status} e {list}, só leitura.", { status: "<code>git status</code>", list: "<code>git worktree list</code>" })}
          ${pending ? `<b class="ag-warn-text">${pending === 1 ? t("1 branch precisa de atenção.") : t("{n} branches precisam de atenção.", { n: pending })}</b>` : ""}</span>
          <span class="spacer"></span><button class="btn btn-sm" data-action="reload">${icon("restart")}<span>${t("Atualizar")}</span></button></div>
        ${this.projects.length ? this.projects.map((p, pi) => `
          <section class="panel ag-panel">
            <div class="panel-head">${icon("folder")}<h2>${esc(p.project)}</h2><span class="dim hint mono">${esc(shortPath(p.root))}</span>
              <span class="spacer"></span>${p.is_repo ? `<span class="dim hint">${t("aberto em {branch}", { branch: `<span class="mono">${esc(p.current_branch || "?")}</span>` })}</span>` : `<span class="badge">${t("sem git")}</span>`}</div>
            ${p.rows.map((r, ri) => this.row(p, r, pi, ri)).join("")}
          </section>`).join("")
          : `<div class="empty-inline">${icon("info")}<span>${t("Nenhuma sessão de agente ainda: os branches aparecem aqui quando houver sessões.")}</span></div>`}
      </div>`;
  }

  row(p, r, pi, ri) {
    const detail = [r.dirty ? (r.dirty === 1 ? t("1 arquivo alterado") : t("{n} arquivos alterados", { n: r.dirty })) : "",
      r.ahead ? (r.ahead === 1 ? t("1 commit à frente") : t("{n} commits à frente", { n: r.ahead })) : ""].filter(Boolean).join(" · ");
    return `<div class="ag-br-row">
      <div class="ag-br-name">${icon(r.worktree ? "tree" : "branch")}<span class="mono">${esc(r.branch || t("sem branch"))}</span>
        ${r.worktree ? `<span class="ag-pill">${t("worktree {name}", { name: esc(r.worktree) })}</span>` : ""}${r.orphan_worktree ? `<span class="ag-pill is-warn">${t("sem sessão")}</span>` : ""}</div>
      <div class="ag-br-state">
        <span class="ag-pill ${TONE[r.state] || ""}">${esc(STATE_LABEL[r.state] || r.state)}</span>
        ${r.stale_days ? `<span class="ag-pill is-err">${icon("alert")}${t("parada há {n} dias", { n: r.stale_days })}</span>` : ""}
        ${detail ? `<span class="dim hint">${esc(detail)}</span>` : ""}
        ${r.state === "PR aberto" && !prEnabled() ? `<span class="dim hint">${t("pelos comandos da sessão")}</span>` : ""}
        ${prEnabled() && r.path ? `<span data-pr-row="${esc(r.path)}"></span>` : ""}
        ${r.sessions.map((s) => `<button type="button" class="ag-pill ag-pill-btn" data-open="${esc(s.id)}" title="${t("Abrir sessão")}">${agentMark(s.agent)}${esc(relTime(s.last_activity_at))}</button>`).join("")}
      </div>
      <div class="ag-br-actions">
        ${BAD.includes(r.state) ? `<button class="btn btn-sm" data-copy="${pi}:${ri}">${icon("copy")}<span>${t("Copiar prompt de conciliação")}</span></button>` : ""}
        <button class="icon-btn" data-folder="${esc(r.path)}" title="${t("Abrir pasta")}" aria-label="${t("Abrir pasta")}">${icon("folder")}</button>
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
      copy(conciliationPrompt(project.rows[ri], project), t("Prompt de conciliação copiado. Cole no terminal da sessão."));
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
