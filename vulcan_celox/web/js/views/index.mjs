// Índice screen: general index, general AI documentation and per-session documentation.

import { documentGeneral, documentSession, onJobsChange } from "../ai.mjs";
import { get, post } from "../api.mjs";
import { $, esc, icon, reportError } from "../dom.mjs";
import { t } from "../i18n.mjs";
import { renderMarkdown } from "../markdown.mjs";
import { sessionHash } from "../session-tree.mjs";

function stamp(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export class IndexView {
  /** @param {{navigate: Function}} options */
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.tab = "index";
    this.config = null;
    this.sessions = [];
    this.running = new Set();
    this.docs = { index: null, documentation: null };
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.offJobs = onJobsChange(() => this.load());
    this.renderShell();
    this.load();
  }

  async load() {
    try {
      const [config, sessions, index, jobs] = await Promise.all([
        get("/api/ai/config"), get("/api/sessions?site=*"), get("/api/index/general"), get("/api/ai/jobs"),
      ]);
      this.config = config;
      this.sessions = [...sessions.open, ...sessions.closed];
      this.docs.index = index;
      this.running = new Set(jobs.jobs.filter((j) => j.status === "running").map((j) => j.target));
      this.docs.documentation = await get("/api/index/documentation").catch(() => null);
      if (!this.root.isConnected) return; // the screen was switched while loading
      this.render();
    } catch (err) {
      reportError(err);
    }
  }

  renderShell() {
    this.root.innerHTML = `
      <div class="page index-page">
        <div class="index-grid">
          <section class="panel index-main">
            <header class="panel-head">
              <div class="segmented" role="tablist" aria-label="${t("Documento")}">
                <button class="seg is-on" role="tab" data-doc-tab="index" aria-selected="true">${icon("book")}<span>${t("Índice geral")}</span></button>
                <button class="seg" role="tab" data-doc-tab="documentation" aria-selected="false">${icon("note")}<span>${t("Documentação")}</span></button>
              </div>
              <div class="spacer"></div>
              <div class="index-actions" data-role="doc-actions"></div>
            </header>
            <article class="index-doc md" data-role="doc"><div class="loading"><span class="skeleton w-40"></span><span class="skeleton w-70"></span></div></article>
          </section>
          <aside class="index-side">
            <section class="panel">
              <header class="panel-head"><h2>${t("Sessões")}</h2><span class="count" data-role="session-count"></span></header>
              <ul class="index-sessions" data-role="sessions"></ul>
            </section>
          </aside>
        </div>
      </div>`;
  }

  render() {
    this.root.querySelectorAll("[data-doc-tab]").forEach((b) => {
      const on = b.dataset.docTab === this.tab;
      b.classList.toggle("is-on", on);
      b.setAttribute("aria-selected", String(on));
    });
    this.renderDoc();
    this.renderSessions();
  }

  renderDoc() {
    const actions = $("[data-role=doc-actions]", this.root);
    const article = $("[data-role=doc]", this.root);
    const configured = this.config && this.config.configured;
    const generalRunning = this.running.has("all");
    if (this.tab === "index") {
      const index = this.docs.index;
      actions.innerHTML = index ? `<button class="btn btn-ghost btn-sm" data-action="open-file" data-file="${esc(index.path)}">${icon("external")}<span>${t("Abrir arquivo")}</span></button>` : "";
      article.innerHTML = index ? renderMarkdown(index.markdown) : "";
      return;
    }
    const doc = this.docs.documentation;
    const generate = `<button class="btn ${doc ? "btn-ghost btn-sm" : "btn-primary"}" data-action="generate-general" ${generalRunning || !this.sessions.length ? "disabled" : ""}>
        ${icon("book")}<span>${generalRunning ? t("Gerando…") : doc ? t("Gerar de novo") : t("Gerar documentação geral")}</span></button>`;
    actions.innerHTML = doc
      ? `<button class="btn btn-ghost btn-sm" data-action="open-file" data-file="${esc(doc.path)}">${icon("external")}<span>${t("Abrir arquivo")}</span></button>${generate}`
      : "";
    article.innerHTML = doc ? renderMarkdown(doc.markdown) : `
      <div class="index-empty">
        <h3>${t("A documentação geral ainda não existe")}</h3>
        <p>${t("A IA lê as sessões de terminal (e as documentações de sessão já geradas) e escreve um documento por site, com linha do tempo, decisões, pendências e comandos recorrentes, gravado em {file}.", { file: "<code>DOCUMENTACAO.md</code>" })}</p>
        ${configured ? generate : `<p class="dim">${t("Cadastre a chave da Anthropic em {link} para começar.", { link: `<a href="#/config">${t("Configurações")}</a>` })}</p>`}
        ${!this.sessions.length ? `<p class="dim">${t("Abra e use um terminal primeiro: sem sessões não há o que documentar.")}</p>` : ""}
      </div>`;
  }

  renderSessions() {
    const list = $("[data-role=sessions]", this.root);
    $("[data-role=session-count]", this.root).textContent = this.sessions.length || "";
    list.innerHTML = this.sessions.length ? this.sessions.map((s) => {
      const busy = this.running.has(s.id);
      return `
        <li class="index-session">
          <a class="index-session-link" href="${sessionHash(s)}">
            ${icon(s.open ? "terminal" : "clock")}
            <span class="index-session-title">${esc(s.title)}</span>
            <span class="index-session-meta">${esc(s.site || "Global")} · ${stamp(s.created_at)}</span>
          </a>
          ${s.has_doc ? `<a class="index-doc-badge" href="${sessionHash(s)}" title="${t("Tem documentação")}">${icon("book")}</a>` : ""}
          <button class="btn btn-ghost btn-sm" data-action="document" data-id="${s.id}" data-title="${esc(s.title)}" ${busy ? "disabled" : ""}>
            ${busy ? t("Gerando…") : s.has_doc ? t("Refazer") : t("Documentar")}</button>
        </li>`;
    }).join("") : `<li class="empty-inline">${icon("terminal")}<span>${t("Nenhuma sessão ainda.")}</span></li>`;
  }

  async onClick(event) {
    const tab = event.target.closest("[data-doc-tab]");
    if (tab) {
      this.tab = tab.dataset.docTab;
      this.render();
      return;
    }
    const link = event.target.closest(".index-doc .md-link");
    if (link) return this.followLink(link.dataset.href);
    const target = event.target.closest("[data-action]");
    if (!target) return;
    const action = target.dataset.action;
    try {
      if (action === "open-file") await post("/api/open", { kind: "file", target: target.dataset.file });
      if (action === "generate-general") {
        const job = await documentGeneral();
        if (job) { this.running.add("all"); this.renderDoc(); }
      }
      if (action === "document") {
        const job = await documentSession(target.dataset.id, target.dataset.title);
        if (job) { this.running.add(target.dataset.id); this.renderSessions(); }
      }
    } catch (err) {
      reportError(err);
    }
  }

  /** Relative links in the index point to memories and documentations: opens the matching session in the app. */
  followLink(href) {
    if (!href) return;
    if (/DOCUMENTACAO\.md$/.test(href)) { this.tab = "documentation"; this.render(); return; }
    const decode = (text) => { try { return decodeURIComponent(text); } catch (_) { return text; } };
    const name = decode(href.split("/").pop()).replace(/\.doc\.md$|\.md$/, "");
    const session = this.sessions.find((s) => s.memory_file && s.memory_file.split("/").pop().replace(/\.md$/, "") === name);
    if (session) this.options.navigate(sessionHash(session));
    else if (this.docs.index) post("/api/open", { kind: "file", target: this.docs.index.path.replace(/INDICE\.md$/, decode(href)) }).catch(reportError);
  }

  destroy() {
    this.offJobs();
  }
}
