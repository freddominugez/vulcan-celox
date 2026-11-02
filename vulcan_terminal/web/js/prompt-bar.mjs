// Barra de prompts fixados na área de terminal (vt-17 C4): com a aba pareada a uma sessão de agente (vt-18 C3), um
// clique cola o texto no terminal sem Enter (vt-27 C3); sem par ou com variável faltando, copia.

import { get, post, put } from "./api.mjs";
import { esc, icon, toast } from "./dom.mjs";
import { AGENT_NAMES, copy } from "./agents-ui.mjs";

const FRESH_MS = 10000;

export class PromptBar {
  constructor(el) {
    this.el = el;
    this.cwd = null;
    this.terminal = null;
    this.data = null;
    this.fetchedAt = 0;
    this.el.addEventListener("click", (e) => this.onClick(e));
    this.onCurrent = () => this.update(this.cwd, this.terminal, true);
    window.addEventListener("vulcan-current-changed", this.onCurrent);
  }

  /** Chamado a cada desenho das abas: só consulta o servidor quando a aba muda ou depois de 10 s. */
  async update(cwd, terminal = null, force = false) {
    if (!cwd) {
      this.cwd = null;
      this.terminal = null;
      this.el.hidden = true;
      return;
    }
    const tabChanged = terminal !== this.terminal;
    if (!force && !tabChanged && Date.now() - this.fetchedAt < FRESH_MS) return;
    this.cwd = cwd;
    this.terminal = terminal;
    this.fetchedAt = Date.now();
    try {
      const params = new URLSearchParams({ pinned: "1", cwd });
      if (terminal) params.set("terminal", terminal);
      this.data = await get(`/api/prompts?${params}`);
    } catch {
      this.el.hidden = true;
      return;
    }
    if (this.terminal !== terminal) return;  // a aba mudou enquanto a resposta vinha
    this.render();
    if (tabChanged) this.followPairedSession(terminal);
  }

  /** D-007: focar uma aba pareada torna a sessão de agente dela a sessão atual. */
  async followPairedSession(terminal) {
    const s = this.data && this.data.session;
    if (!s || s.pairing_id !== terminal) return;
    try {
      const current = await get("/api/agents/current");
      if (current.session && current.session.id === s.id) return;  // já é a atual: nada a fazer
      const data = await put("/api/agents/current", { session_id: s.id });
      window.dispatchEvent(new CustomEvent("vulcan-current-changed", { detail: data }));
    } catch {
      /* sem sessão atual agora: a barra continua com a sessão pareada */
    }
  }

  render() {
    const d = this.data;
    if (!d.prompts.length) {
      this.el.hidden = true;
      return;
    }
    const s = d.session;
    const who = s ? `${s.pairing_id === this.terminal ? "pareada · " : ""}${esc(s.project || "sem projeto")}${s.branch ? ` · ${esc(s.branch)}` : ""} · ${esc(AGENT_NAMES[s.agent] || s.agent)}` : "sem sessão de agente";
    this.el.hidden = false;
    this.el.innerHTML = `<span class="pb-label" title="Variáveis preenchidas com esta sessão de agente">${icon("text")}<span>${who}</span></span>
      ${d.prompts.map((p) => `<button type="button" class="pb-chip ${p.missing.length ? "is-missing" : ""}" data-prompt="${esc(p.id)}"
        title="${esc(this.canSend(p) ? `Colar no terminal (sem Enter): ${p.summary}` : `Copiar: ${p.summary}`)}">${icon(this.canSend(p) ? "terminal" : "copy")}<span>${esc(p.title)}</span></button>`).join("")}
      <a class="pb-more" href="#/prompts">Todos…</a>`;
  }

  /** Colar direto só quando a sessão é a pareada com esta aba e nenhuma variável falta. */
  canSend(p) {
    const s = this.data && this.data.session;
    return Boolean(s && s.pairing_id && s.pairing_id === this.terminal && !p.missing.length);
  }

  async onClick(event) {
    const chip = event.target.closest("[data-prompt]");
    if (!chip) return;
    const p = this.data.prompts.find((x) => x.id === chip.dataset.prompt);
    if (!p) return;
    if (this.canSend(p)) {
      try {
        await post("/api/prompts/send", { prompt: p.id, session: this.data.session.id, values: {} });
        toast(`${p.title}: texto colado no terminal. Revise e aperte Enter.`, { kind: "ok" });
        chip.classList.add("is-done");
        setTimeout(() => chip.classList.remove("is-done"), 1200);
        return;
      } catch {
        /* sem aba viva: cai na cópia */
      }
    }
    const ok = await copy(p.rendered, `Copiado: ${p.title}. Cole no terminal com ⌘V.`);
    if (ok) {
      chip.classList.add("is-done");
      setTimeout(() => chip.classList.remove("is-done"), 1200);
    }
  }

  destroy() {
    window.removeEventListener("vulcan-current-changed", this.onCurrent);
  }
}
