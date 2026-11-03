// Botão "Sessão atual" da barra superior: os prompts usam os dados desta sessão.
// Padrão: a mais recente (ativa primeiro); um clique troca. Avisa as telas com o evento "vulcan-current-changed".

import { get, put } from "./api.mjs";
import { esc, icon, reportError, toast } from "./dom.mjs";
import { AGENT_NAMES, agentMark, relTime } from "./agents-ui.mjs";

export class CurrentSession {
  constructor(root) {
    this.root = root;
    this.data = null;
    this.root.addEventListener("click", (e) => {
      if (e.target.closest("[data-current-toggle]")) this.toggle();
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest("#current-session")) this.close();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") this.close();
    });
  }

  async refresh() {
    try {
      const data = await get("/api/agents/current");
      const changed = !this.data || (this.data.session && this.data.session.id) !== (data.session && data.session.id);
      this.data = data;
      this.render();
      if (changed) window.dispatchEvent(new CustomEvent("vulcan-current-changed", { detail: data }));
    } catch {
      /* sem servidor agora: tenta no próximo ciclo */
    }
  }

  render() {
    const s = this.data && this.data.session;
    const open = this.root.querySelector(".cs-pop");
    if (!s) {
      this.root.innerHTML = "";
      return;
    }
    this.root.innerHTML = `<button type="button" class="cs-btn t-${esc(s.theme || "neutro")}" data-current-toggle aria-haspopup="listbox"
        title="Sessão atual: os prompts usam os dados dela. Clique para trocar.">
      <span class="dot ${s.is_active ? "dot-ok" : ""}"></span><span class="cs-label">Sessão atual</span>
      <span class="cs-proj">${esc(s.project || "sem projeto")}</span>${s.branch ? `<span class="cs-branch">${esc(s.branch)}</span>` : ""}
      ${agentMark(s.agent)}${icon("chevron-down", "i-sm")}</button>`;
    if (open) this.toggle(true);
  }

  close() {
    const pop = this.root.querySelector(".cs-pop");
    if (pop) pop.remove();
  }

  async toggle(reopen = false) {
    if (!reopen && this.root.querySelector(".cs-pop")) return this.close();
    let list = [];
    try {
      list = (await get("/api/agents/sessions")).sessions.slice(0, 40);
    } catch (err) {
      return reportError(err);
    }
    const current = this.data && this.data.session ? this.data.session.id : null;
    const auto = this.data && this.data.automatic;
    const pop = document.createElement("div");
    pop.className = "cs-pop";
    pop.setAttribute("role", "listbox");
    pop.innerHTML = `
      <div class="cs-group">Sessão atual dos prompts</div>
      <button type="button" class="cs-opt ${auto ? "is-on" : ""}" data-pick="">${icon("restart")}<span class="cs-tx"><b>Automática</b>
        <span>a mais recente, com as ativas primeiro</span></span>${auto ? icon("check") : ""}</button>
      ${list.map((s) => `<button type="button" class="cs-opt ${!auto && s.id === current ? "is-on" : ""}" data-pick="${esc(s.id)}" role="option">
        <span class="dot ${s.is_active ? "dot-ok" : ""}"></span><span class="cs-tx"><b>${esc(s.project || "sem projeto")}</b>
        <span>${esc(s.branch || "sem branch")} · ${esc(AGENT_NAMES[s.agent] || s.agent)} · ${esc(relTime(s.last_activity_at))}</span></span>
        ${!auto && s.id === current ? icon("check") : ""}</button>`).join("")}`;
    pop.addEventListener("click", (e) => {
      const opt = e.target.closest("[data-pick]");
      if (opt) this.pick(opt.dataset.pick || null);
    });
    this.close();
    this.root.appendChild(pop);
    return null;
  }

  async pick(sessionId) {
    try {
      this.data = await put("/api/agents/current", { session_id: sessionId });
      this.close();
      this.render();
      const s = this.data.session;
      toast(sessionId ? `Sessão atual: ${s.project} · ${s.branch || "sem branch"}` : "Sessão atual automática.", { kind: "ok" });
      window.dispatchEvent(new CustomEvent("vulcan-current-changed", { detail: this.data }));
    } catch (err) {
      reportError(err);
    }
  }
}
