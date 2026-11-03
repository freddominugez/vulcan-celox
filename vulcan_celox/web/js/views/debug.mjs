// Tela Depuração: eventos da ponte de dumps do Lerd agrupados por requisição, com filtros, o interruptor
// da ponte e a origem de cada evento. Global (#/depuracao) ou presa a um site (aba Depuração do site).

import { every, get, post, put } from "../api.mjs";
import { esc, icon, reportError, toast } from "../dom.mjs";
import { copy } from "../agents-ui.mjs";
import { t } from "../i18n.mjs";

const KINDS = [["", t("Todos os tipos")], ["dump", "dump()"], ["query", t("Queries")], ["log", t("Logs e exceções")],
  ["view", t("Views")], ["request", t("Requisições")]];

function shortFile(path) {
  return path.split("/").slice(-3).join("/");
}

export class DebugView {
  constructor(root, options) {
    this.root = root;
    this.site = options.site || null;  // aba do site: filtro de site fixo
    this.sites = options.sites || [];
    this.filters = { site: this.site ? this.site.name : "", kind: "", q: "", min_ms: "" };
    this.groups = [];
    this.bridge = null;
    this.root.innerHTML = `<div class="debug">
      <div class="debug-bar">
        <button class="btn btn-sm debug-bridge" data-dbg="bridge" aria-pressed="false">${icon("dot")}<span>${t("Ponte")}</span></button>
        ${this.site ? "" : `<select class="select" data-filter="site" aria-label="${t("Site")}"><option value="">${t("Todos os sites")}</option>
          ${this.sites.map((s) => `<option value="${esc(s.name)}">${esc(s.name)}</option>`).join("")}</select>`}
        <select class="select" data-filter="kind" aria-label="${t("Tipo")}">${KINDS.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select>
        <input class="input debug-minms" data-filter="min_ms" type="number" min="0" step="10" placeholder="${t("ms mín.")}" title="${t("Só queries a partir deste tempo")}" aria-label="${t("Tempo mínimo das queries em ms")}">
        <input class="input debug-search" data-filter="q" placeholder="${t("Buscar em dumps, SQL e mensagens")}" spellcheck="false" aria-label="${t("Buscar")}">
        <span class="spacer"></span>
        <span class="dim debug-count" data-count></span>
        <button class="btn btn-sm" data-dbg="clear" title="${t("Limpa os eventos guardados pelo Lerd")}">${t("Limpar")}</button>
      </div>
      <p class="debug-note dim" data-note></p>
      <div class="debug-body" role="log" aria-live="polite"></div>
    </div>`;
    this.body = this.root.querySelector(".debug-body");
    this.root.querySelectorAll("[data-filter]").forEach((el) => {
      el.addEventListener(el.tagName === "INPUT" ? "input" : "change", () => {
        this.filters[el.dataset.filter] = el.value.trim();
        this.load();
      });
    });
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.stopTimer = every(2000, () => this.load());
    this.load();
  }

  query() {
    const p = new URLSearchParams({ group: "1", limit: "500" });
    Object.entries(this.filters).forEach(([k, v]) => { if (v) p.set(k, v); });
    return p.toString();
  }

  async load() {
    try {
      const [bridge, data] = await Promise.all([get("/api/debug/bridge"), get(`/api/debug/events?${this.query()}`)]);
      // Redesenha só quando algo mudou, e nunca com texto selecionado no corpo (copiar um dump)
      const signature = JSON.stringify([bridge.enabled, bridge.count, this.query(),
        data.groups.map((g) => g.events.map((e) => e.id || e.ts).join(","))]);
      if (signature === this.signature) return;
      if (this.selecting()) return;  // fica para a próxima volta, depois que a seleção acabar
      this.signature = signature;
      this.bridge = bridge;
      this.groups = data.groups;
      this.draw();
    } catch (err) {
      if (err.status === 409) this.unavailable(err.message);
      else reportError(err);
    }
  }

  selecting() {
    const sel = window.getSelection();
    return Boolean(sel && !sel.isCollapsed && sel.anchorNode && this.body.contains(sel.anchorNode));
  }

  unavailable(message) {
    this.stopTimer();
    this.root.innerHTML = `<div class="page"><div class="empty-block"><h3>${t("Depuração indisponível")}</h3><p>${esc(message)}.</p></div></div>`;
  }

  draw() {
    const b = this.bridge;
    const btn = this.root.querySelector("[data-dbg=bridge]");
    btn.setAttribute("aria-pressed", String(b.enabled));
    btn.classList.toggle("is-on", b.enabled);
    btn.querySelector("span").textContent = b.enabled ? t("Ponte ligada") : t("Ponte desligada");
    btn.title = t("Liga e desliga a captura de dump(), queries e logs em todas as versões de PHP do Lerd");
    this.root.querySelector("[data-note]").textContent = b.enabled
      ? t("Capturando em todas as versões de PHP. {count} de {capacity} eventos guardados pelo Lerd.", { count: b.count, capacity: b.capacity })
      : t("A ponte está desligada: ligue para ver dump(), queries e logs aqui. Vale para todas as versões de PHP.");
    const total = this.groups.reduce((n, g) => n + g.events.length, 0);
    this.root.querySelector("[data-count]").textContent = total ? t("{events} eventos em {groups} requisições", { events: total, groups: this.groups.length }) : "";
    if (!this.groups.length) {
      this.body.innerHTML = `<p class="dim debug-empty">${b.enabled ? t("Nenhum evento com esse filtro.") : ""}</p>`;
      return;
    }
    this.body.innerHTML = this.groups.map((g) => this.groupHtml(g)).join("");
  }

  groupHtml(g) {
    // SQL repetido na mesma requisição ganha marca com contagem e tempo somado
    this.repeated = new Map((g.queries || []).filter((q) => q.count > 1).map((q) => [q.sql, q]));
    const reps = [...this.repeated.values()].map((q) => `<div class="debug-repeat"><span class="badge badge-warn">${q.count}×</span>
        <code class="debug-sql">${esc(q.sql)}</code><span class="dim">${t("{ms} ms no total", { ms: q.total_ms })}</span></div>`).join("");
    const where = g.branch ? `${g.site}@${g.branch}` : g.site;
    const counts = Object.entries(g.counts).map(([k, n]) => `<span class="badge">${esc(k)} ${n}</span>`).join("");
    return `<section class="debug-group">
      <header class="debug-group-head">${this.site ? "" : `<span class="debug-site">[${esc(where)}]</span>`}
        <code class="debug-req">${esc(g.request || t("(sem requisição)"))}</code><span class="dim">${esc(g.ts.slice(11, 19))}</span>
        <span class="spacer"></span>${counts}</header>
      ${reps ? `<div class="debug-repeats">${reps}</div>` : ""}
      ${g.events.map((e) => this.eventHtml(e)).join("")}
    </section>`;
  }

  eventHtml(e) {
    const src = e.file ? `<span class="debug-src">
        <button class="link-btn" data-open="${esc(e.file)}" title="${t("Abrir {file} no editor", { file: esc(e.file) })}">${esc(shortFile(e.file))}:${e.line}</button>
        <button class="icon-btn icon-btn-sm" data-copy="${esc(e.file)}" aria-label="${t("Copiar caminho")}" title="${t("Copiar caminho")}">${icon("copy")}</button></span>` : "";
    const tone = e.tone ? ` log-${esc(e.tone)}` : "";
    return `<div class="debug-event k-${esc(e.kind)}${tone}"><span class="debug-kind">${esc(e.kind)}</span>
      <div class="debug-main">${this.detail(e)}</div>${src}</div>`;
  }

  detail(e) {
    const d = e.data || {};
    if (e.kind === "query") {
      const rep = this.repeated && this.repeated.get(d.sql || "");
      return `<code class="debug-sql">${esc(d.sql || "")}</code> <span class="dim">${esc(String(d.time_ms ?? ""))} ms</span>${rep ? ` <span class="badge badge-warn" title="${t("Mesma query {n} vezes nesta requisição", { n: rep.count })}">${t("repetida {n}×", { n: rep.count })}</span>` : ""}`;
    }
    if (e.kind === "log") return `<span class="debug-level log-level">${esc(d.level || "")}</span> <span class="log-msg">${esc(d.message || "")}</span>`;
    if (e.kind === "request") return `<span class="dim">${esc(String(d.time_ms ?? ""))} ms · ${Math.round((d.memory_peak || 0) / 1048576)} MB</span>`;
    if (e.kind === "view") return `<span>${esc(d.name || d.view || e.label || "")}</span>`;
    // dump e tipos que o Lerd venha a criar: o texto como veio
    return `<pre class="debug-dump">${esc(e.text || e.label || JSON.stringify(d, null, 2))}</pre>`;
  }

  async onClick(event) {
    const tg = event.target.closest("[data-dbg], [data-open], [data-copy]");
    if (!tg) return;
    try {
      if (tg.dataset.dbg === "bridge") {
        this.bridge = await put("/api/debug/bridge", { enabled: !this.bridge.enabled });
        this.signature = null;
        toast(this.bridge.enabled ? t("Ponte de dumps ligada em todas as versões de PHP.") : t("Ponte de dumps desligada."), { kind: "ok" });
        this.draw();
      }
      if (tg.dataset.dbg === "clear") {
        await post("/api/debug/clear");
        this.signature = null;
        await this.load();
      }
      if (tg.dataset.open) await post("/api/open", { kind: "source", target: tg.dataset.open });
      if (tg.dataset.copy) await copy(tg.dataset.copy, t("Caminho copiado."));
    } catch (err) {
      reportError(err);
    }
  }

  destroy() {
    this.stopTimer();
  }
}
