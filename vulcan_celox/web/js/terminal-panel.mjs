// Painel inferior de terminal: abaixo das telas que não têm terminal, com as abas de todos os
// terminais. ⌘J mostra e esconde, a borda de cima arrasta, a altura fica lembrada. Nas telas de site e Terminais o
// terminal já ocupa a área principal: o painel se recolhe e devolve os terminais (um xterm só fica num lugar).

import { isMac } from "./api.mjs";
import { icon } from "./dom.mjs";
import { t } from "./i18n.mjs";
import { terminals, TerminalWorkspace } from "./terminals.mjs";

const KEY = "vulcan-celox-panel";
const MIN = 38;
const DEFAULT_HEIGHT = 280;
const HIDDEN_ON = ["site", "terminals", "popout"];

function load() {
  try {
    const data = JSON.parse(localStorage.getItem(KEY) || "{}");
    return { open: data.open !== false, height: Number(data.height) || DEFAULT_HEIGHT };
  } catch {
    return { open: true, height: DEFAULT_HEIGHT };
  }
}

export class TerminalPanel {
  constructor(el, options) {
    this.el = el;
    this.options = options;
    this.state = load();
    this.ws = null;
    this.route = null;
    this.el.innerHTML = `
      <div class="tp-grip" title="${t("Arraste para mudar a altura")}" aria-hidden="true"></div>
      <div class="tp-head">
        <button type="button" class="tp-title" data-tp="toggle" title="${t("Mostrar ou esconder o terminal ({key})", { key: isMac ? "⌘J" : "Ctrl+⇧+J" })}">
          ${icon("terminal")}<span>${t("Terminal")}</span><span class="count" data-tp-count></span></button>
        <span class="spacer"></span>
        <kbd class="tp-kbd">${isMac ? "⌘J" : "Ctrl+⇧+J"}</kbd>
        <button type="button" class="icon-btn icon-btn-sm" data-tp="toggle" aria-label="${t("Minimizar ou mostrar o terminal")}" title="${t("Minimizar ou mostrar")}">
          <span data-tp-chevron>${icon("chevron-down")}</span></button>
      </div>
      <div class="tp-body"></div>`;
    this.body = this.el.querySelector(".tp-body");
    this.el.addEventListener("click", (e) => {
      if (e.target.closest("[data-tp=toggle]")) this.toggle();
    });
    this.bindGrip();
    this.unsubscribe = terminals.subscribe(() => this.updateCount());
    this.apply();
  }

  save() {
    try {
      localStorage.setItem(KEY, JSON.stringify(this.state));
    } catch {
      /* sem armazenamento: só não lembra */
    }
  }

  maxHeight() {
    return Math.max(MIN, Math.round(window.innerHeight * 0.7));
  }

  apply() {
    const hidden = HIDDEN_ON.includes(this.route);
    this.el.hidden = hidden;
    this.el.classList.toggle("is-open", this.state.open);
    this.el.style.height = this.state.open ? `${Math.min(this.maxHeight(), Math.max(MIN, this.state.height))}px` : `${MIN}px`;
    this.el.querySelector("[data-tp-chevron]").innerHTML = icon(this.state.open ? "chevron-down" : "chevron-up");
    this.updateCount();
  }

  updateCount() {
    const n = terminals.list().length;
    this.el.querySelector("[data-tp-count]").textContent = n ? String(n) : "";
  }

  /** Chamado a cada troca de tela: monta o workspace nas telas sem terminal e o desmonta nas outras. */
  setRoute(name) {
    this.route = name;
    if (HIDDEN_ON.includes(name)) {
      this.unmount();
    } else if (!this.ws) {
      this.ws = new TerminalWorkspace(this.body, { site: null, scope: "all", mode: "terminal", sites: this.options.sites() });
    }
    this.apply();
  }

  unmount() {
    if (this.ws) {
      this.ws.destroy();  // devolve os xterm ao conjunto; os processos continuam vivos
      this.ws = null;
      this.body.innerHTML = "";
    }
  }

  get available() {
    return !HIDDEN_ON.includes(this.route);
  }

  toggle(force = null) {
    this.state.open = force === null ? !this.state.open : force;
    this.save();
    this.apply();
    if (this.state.open && this.ws) {
      const active = terminals.get(this.ws.activeId);
      if (active) setTimeout(() => active.focus(), 0);
    }
  }

  /** ⌘F com o painel aberto: busca no terminal ativo do painel. */
  find() {
    if (!this.ws || !this.state.open) return false;
    return this.ws.openSearch();
  }

  /** ⌘T nas telas sem terminal: abre no painel, sem sair da tela. */
  async newTerminal(options = {}) {
    if (!this.ws) return null;
    this.toggle(true);
    return this.ws.newTerminal(null, null, options);
  }

  bindGrip() {
    const grip = this.el.querySelector(".tp-grip");
    let startY = null;
    let startH = 0;
    grip.addEventListener("pointerdown", (e) => {
      startY = e.clientY;
      startH = this.el.getBoundingClientRect().height;
      grip.setPointerCapture(e.pointerId);
      this.el.classList.add("is-dragging");
    });
    grip.addEventListener("pointermove", (e) => {
      if (startY === null) return;
      const h = Math.min(this.maxHeight(), Math.max(MIN, startH + (startY - e.clientY)));
      this.state.open = h > MIN + 20;
      this.state.height = this.state.open ? h : this.state.height;
      this.el.style.height = `${h}px`;
    });
    const end = () => {
      if (startY === null) return;
      startY = null;
      this.el.classList.remove("is-dragging");
      this.save();
      this.apply();
    };
    grip.addEventListener("pointerup", end);
    grip.addEventListener("pointercancel", end);
  }

  destroy() {
    this.unsubscribe();
    this.unmount();
  }
}
