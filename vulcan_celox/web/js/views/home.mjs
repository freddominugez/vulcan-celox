// Início screen, the app's opening: what is still missing to set up and a card for each item of the app.
// It opens with the app until the user checks the box; afterwards it stays in the sidebar and in Settings.

import { brandLogo } from "../brand.mjs";
import { installLerd } from "../lerd-setup.mjs";
import { get, isMac, put } from "../api.mjs";
import { NAV_GROUPS, lerdUnavailable, navById } from "../app-state.mjs";
import { esc, icon, reportError } from "../dom.mjs";
import { keyText, t } from "../i18n.mjs";

// parts of the window that are not sidebar items
const WINDOW_PARTS = () => [
  { icon: "search", title: t("Busca"), text: t("Ache sites, tarefas e sessões, rode comandos e abra qualquer tela, mesmo as escondidas. Atalho: {key}.", { key: isMac ? "⌘K" : "Ctrl+⇧+K" }) },
  { icon: "spark", title: t("Sessão atual"), text: t("No alto: o agente e o branch da sessão em foco. Os prompts usam esses dados.") },
  { icon: "database", title: t("Estado do ambiente"), text: t("No alto, à direita: mostra se o Lerd está rodando, com botões para ligar, parar e reiniciar. Sem Lerd, some.") },
  { icon: "terminal", title: t("Painel de terminal"), text: t("Embaixo: terminais sem sair da tela atual. Atalho: {key}.", { key: isMac ? "⌘J" : "Ctrl+⇧+J" }) },
  { icon: "history", title: t("Sessões e listas"), text: t("Abaixo do menu: terminais abertos, histórico dos fechados, sites e projetos Node.") },
  { icon: "help", title: t("Ajuda desta tela"), text: t("O botão ? no alto abre o manual na parte certa da tela em que você está.") },
];

export class HomeView {
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.root.innerHTML = `<div class="loading"><span class="skeleton w-40"></span><span class="skeleton w-70"></span></div>`;
    this.load();
  }

  async load() {
    try {
      this.guide = await get("/api/guide");
      this.render();
      // the agent index is still on its first read: check again shortly (up to 40 times)
      if (this.guide.steps.some((st) => st.lendo) && (this.retries = (this.retries || 0) + 1) <= 40) {
        this.timer = setTimeout(() => this.load(), 500);
      }
    } catch (err) {
      reportError(err);
    }
  }

  destroy() {
    clearTimeout(this.timer);
  }

  greeting() {
    const h = new Date().getHours();
    return h < 12 ? t("Bom dia") : h < 18 ? t("Boa tarde") : t("Boa noite");
  }

  cards() {
    const card = (n) => `<a class="in-area" href="${n.hash}" data-card="${n.id}">
        <span class="in-ic">${icon(n.icon)}</span><b>${esc(n.label)}</b><span class="dim">${esc(n.desc)}</span></a>`;
    return NAV_GROUPS.map((g) => {
      const items = g.items.filter((id) => id !== "inicio" && !(id === "ambiente" && lerdUnavailable())).map((id) => navById[id]);
      return items.length ? `<h3 class="in-group">${esc(g.label || g.title)}</h3><div class="in-areas">${items.map(card).join("")}</div>` : "";
    }).join("");
  }

  render() {
    const g = this.guide;
    const missing = g.steps.filter((s) => !s.ok && !s.optional).length;
    const head = g.done ? t("Tudo pronto. Os passos essenciais estão feitos.")
      : missing === 1 ? t("Falta 1 passo para tudo funcionar.") : t("Faltam {n} passos para tudo funcionar.", { n: missing });
    const action = {
      lerd: this.lerdActions(g.steps.find((s) => s.id === "lerd")),
      projetos: `<button class="btn btn-sm" data-go="#/node">${icon("plus")}<span>${t("Adicionar")}</span></button>`,
      agentes: `<button class="btn btn-sm" data-go="#/agentes">${icon("spark")}<span>${t("Ver agentes")}</span></button>`,
      terminal: `<button class="btn btn-primary btn-sm" data-home="terminal">${icon("terminal")}<span>${t("Abrir terminal")}</span></button>`,
    };
    this.root.innerHTML = `<div class="page in-page">
        ${brandLogo()}
      <div class="in-hello">
        <h1>${this.greeting()}. ${esc(head)}</h1>
        <p class="dim">${t("Esta tela mostra o que falta configurar e explica cada parte do app.")}</p>
        <label class="in-dismiss"><input type="checkbox" data-home="dismiss" ${g.skipped ? "checked" : ""}>
          <span>${t("Não mostrar esta tela ao iniciar")} <span class="dim">${t("(ela continua em Início e você pode reativá-la em Configurações)")}</span></span></label>
      </div>
      <ol class="in-steps">${g.steps.map((s, i) => `<li class="in-step ${s.ok ? "is-done" : ""}" data-spot="${s.id}">
          <span class="in-ck" aria-hidden="true">${s.ok ? icon("check") : i + 1}</span>
          <span class="in-step-main"><b>${esc(s.title)}</b><span class="dim">${esc(keyText(s.detail))}</span></span>
          ${s.ok ? `<span class="sr-only">${t("feito")}</span>` : `<span class="in-step-do">${action[s.id] || ""}</span>`}</li>`).join("")}</ol>
      <div class="in-subhead"><h2 class="in-sub">${t("O que cada item faz")}</h2>
        <a class="btn btn-ghost btn-sm" href="#/config" data-card-config>${icon("gear")}<span>${t("Escolher o que aparece na barra lateral")}</span></a></div>
      ${this.cards()}
      <h2 class="in-sub">${t("O resto da janela")}</h2>
      <div class="in-areas">${WINDOW_PARTS().map((a) => `<div class="in-area is-static"><span class="in-ic">${icon(a.icon)}</span><b>${esc(a.title)}</b><span class="dim">${esc(a.text)}</span></div>`).join("")}</div>
      <p class="dim in-help">${t("Dúvidas? Abra {link} (⌘?) ou use o botão ? no alto de cada tela.", { link: `<a href="#/ajuda" data-go="#/ajuda">${t("Ajuda")}</a>` })}</p>
    </div>`;
  }

  lerdActions(step) {
    if (!step) return "";
    if (step.skipped) return `<button class="btn btn-ghost btn-sm" data-home="lerd-use">${t("Usar o Lerd")}</button>`;
    const skip = `<button class="btn btn-ghost btn-sm" data-home="lerd-skip">${t("Não uso")}</button>`;
    if (step.state === "absent") return `<button class="btn btn-sm" data-home="lerd-install">${icon("plus")}<span>${t("Instalar")}</span></button>${skip}`;
    return `<button class="btn btn-sm" data-service="start">${icon("play")}<span>${t("Ligar")}</span></button>${skip}`;
  }

  async onClick(event) {
    const btn = event.target.closest("[data-home]");
    try {
      if (btn && btn.dataset.home === "dismiss") {
        this.guide = await put("/api/guide", { skipped: btn.checked });
        return this.render();
      }
      if (btn && btn.dataset.home === "lerd-install") return installLerd();
      if (btn && (btn.dataset.home === "lerd-skip" || btn.dataset.home === "lerd-use")) {
        this.guide = await put("/api/guide", { lerd_skipped: btn.dataset.home === "lerd-skip" });
        return this.render();
      }
      if (btn && btn.dataset.home === "terminal") {
        if (window.vulcanCommand) await window.vulcanCommand("newTerminal");
        return setTimeout(() => this.load(), 1500);
      }
    } catch (err) {
      reportError(err);
    }
    return null;
  }
}
