// Ajuda screen: manual by topic and frequently asked questions, with search as you type.

import { put } from "../api.mjs";
import { esc, icon, reportError } from "../dom.mjs";
import { t } from "../i18n.mjs";
import { blockHtml, blockText, fold, inline, loadHelp } from "../help-content.mjs";

export class HelpView {
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.section = options.section || null;
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.root.addEventListener("input", (e) => {
      if (e.target.matches(".hp-search input")) this.filter(e.target.value);
    });
    this.root.innerHTML = `<div class="loading"><span class="skeleton w-40"></span><span class="skeleton w-70"></span></div>`;
    this.load();
  }

  async load() {
    try {
      this.data = await loadHelp();
      this.render();
    } catch (err) {
      reportError(err);
    }
  }

  reveal(route) {
    this.section = route.section || null;
    this.scrollTo();
  }

  render() {
    const d = this.data;
    this.root.innerHTML = `<div class="page hp-page">
      <aside class="hp-toc" aria-label="${t("Assuntos da Ajuda")}">
        <a href="#/ajuda/faq" class="hp-toc-item" data-sec="faq">${icon("help")}<span>${t("Perguntas frequentes")}</span></a>
        <div class="hp-toc-label">${t("Manual")}</div>
        ${d.secoes.map((s) => `<a href="#/ajuda/${s.id}" class="hp-toc-item" data-sec="${s.id}"><span>${esc(s.titulo)}</span></a>`).join("")}
        <div class="hp-toc-label">${t("Guia")}</div>
        <button class="hp-toc-item" data-hp="guide">${icon("home")}<span>${t("Ver a tela de abertura")}</span></button>
      </aside>
      <div class="hp-main">
        <label class="hp-search">${icon("search")}<input type="search" placeholder="${t("Procure uma dúvida: porta em uso, custo, Lerd parado")}" aria-label="${t("Buscar na Ajuda")}" spellcheck="false"></label>
        <p class="hp-none dim" hidden>${t("Nada encontrado. Tente outra palavra ou veja as perguntas frequentes.")}</p>
        <section class="hp-sec hp-faq" id="hp-faq" data-sec="faq">
          <h2>${t("Perguntas frequentes")}</h2>
          ${d.faq.map((f) => `<details data-text="${esc(fold(`${f.q} ${f.a}`))}"><summary>${inline(f.q)}</summary>
            <p>${inline(f.a)}</p>${f.secao ? `<a class="hp-more" href="#/ajuda/${f.secao}">${t("Mais em {titulo}", { titulo: esc((d.secoes.find((s) => s.id === f.secao) || {}).titulo || "") })}</a>` : ""}</details>`).join("")}
        </section>
        ${d.secoes.map((s) => `<section class="hp-sec" id="hp-${s.id}" data-sec="${s.id}"
            data-text="${esc(fold(`${s.titulo} ${s.resumo} ${s.blocos.map(blockText).join(" ")}`))}">
          <h2>${esc(s.titulo)}</h2><p class="hp-lead">${esc(s.resumo)}</p>${s.blocos.map(blockHtml).join("")}</section>`).join("")}
      </div>
    </div>`;
    this.scrollTo();
  }

  scrollTo() {
    if (!this.data) return;
    const id = this.section || "faq";
    this.root.querySelectorAll(".hp-toc-item").forEach((a) => a.classList.toggle("is-on", a.dataset.sec === id));
    const el = this.root.querySelector(`#hp-${CSS.escape(id)}`);
    if (el && this.section) {
      el.scrollIntoView({ block: "start" });
      el.classList.add("is-flash");
      setTimeout(() => el.classList.remove("is-flash"), 1200);
    }
  }

  filter(query) {
    const q = fold(query.trim());
    let shown = 0;
    this.root.querySelectorAll(".hp-faq details").forEach((d) => {
      const hit = !q || d.dataset.text.includes(q);
      d.hidden = !hit;
      if (q && hit) d.open = true;
      if (hit) shown += 1;
    });
    const faqHits = shown;
    this.root.querySelector(".hp-faq").hidden = Boolean(q) && !faqHits;
    this.root.querySelectorAll(".hp-sec[data-text]").forEach((s) => {
      const hit = !q || s.dataset.text.includes(q);
      s.hidden = !hit;
      if (hit) shown += 1;
    });
    this.root.querySelector(".hp-none").hidden = shown > 0;
  }

  async onClick(event) {
    if (event.target.closest("[data-hp=guide]")) {
      try {
        await put("/api/guide", { skipped: false });
        this.options.navigate("#/inicio");
      } catch (err) {
        reportError(err);
      }
    }
  }
}
