// Barra de prompts fixados na área de terminal: com a aba pareada a uma sessão de agente, um
// clique cola o texto no terminal sem Enter; sem par ou com variável faltando, copia.

import { get, post, put } from "./api.mjs";
import { esc, icon, toast } from "./dom.mjs";
import { AGENT_NAMES, copy } from "./agents-ui.mjs";
import { t } from "./i18n.mjs";

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

  /** Focar uma aba pareada torna a sessão de agente dela a sessão atual. */
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
    const s = d.session;
    const paired = s && s.pairing_id && s.pairing_id === this.terminal;
    if (!d.prompts.length && !paired) {
      this.el.hidden = true;
      return;
    }
    const who = s ? `${s.pairing_id === this.terminal ? `${t("pareada")} · ` : ""}${esc(s.project || t("sem projeto"))}${s.branch ? ` · ${esc(s.branch)}` : ""} · ${esc(AGENT_NAMES[s.agent] || s.agent)}` : t("sem sessão de agente");
    this.el.hidden = false;
    this.el.innerHTML = `<span class="pb-label" title="${t("Variáveis preenchidas com esta sessão de agente")}">${icon("text")}<span>${who}</span></span>
      ${d.prompts.map((p) => `<button type="button" class="pb-chip ${p.missing.length ? "is-missing" : ""}" data-prompt="${esc(p.id)}"
        title="${esc(this.canSend(p) ? t("Colar no terminal (sem Enter): {summary}", { summary: p.summary }) : t("Copiar: {summary}", { summary: p.summary }))}">${icon(this.canSend(p) ? "terminal" : "copy")}<span>${esc(p.title)}</span></button>`).join("")}
      ${d.prompts.length ? `<a class="pb-more" href="#/prompts">${t("Todos…")}</a>` : ""}
      ${paired ? `<a class="pb-chip pb-code" href="#/agentes/${encodeURIComponent(s.id)}/codigo" title="${t("Ver o código que esta sessão está mexendo")}">${icon("code")}<span>${t("Código")}</span></a>` : ""}`;
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
        toast(t("{title}: texto colado no terminal. Revise e aperte Enter.", { title: p.title }), { kind: "ok" });
        chip.classList.add("is-done");
        setTimeout(() => chip.classList.remove("is-done"), 1200);
        return;
      } catch {
        /* sem aba viva: cai na cópia */
      }
    }
    const ok = await copy(p.rendered, t("Copiado: {title}. Cole no terminal com ⌘V.", { title: p.title }));
    if (ok) {
      chip.classList.add("is-done");
      setTimeout(() => chip.classList.remove("is-done"), 1200);
    }
  }

  destroy() {
    window.removeEventListener("vulcan-current-changed", this.onCurrent);
  }
}
