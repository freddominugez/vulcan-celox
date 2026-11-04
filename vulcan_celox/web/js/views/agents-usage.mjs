// Agent usage: tokens and estimated cost at API price by day, project, model and session.

import { get, token } from "../api.mjs";
import { esc, icon, reportError } from "../dom.mjs";
import { currentLanguage, t } from "../i18n.mjs";
import { AGENT_NAMES, agentMark, copy, RevisionWatch } from "../agents-ui.mjs";

const PERIODS = [7, 30, 90];
// per-agent colors validated against the dark surface (#202024): luminosity range, chroma, color blindness and contrast
const AGENT_ORDER = ["claude", "codex"];

const decimal = (v) => (currentLanguage() === "pt" ? v.replace(".", ",") : v);

export function fmtTokens(n) {
  n = n || 0;
  if (n >= 1e9) return t("{n} bi", { n: decimal((n / 1e9).toFixed(1)) });
  if (n >= 1e6) return t("{n} mi", { n: decimal((n / 1e6).toFixed(1)) });
  if (n >= 1000) return t("{n} mil", { n: Math.round(n / 1000) });
  return String(n);
}

export function fmtCost(c, partial = false) {
  if (c === null || c === undefined) return t("sem preço");
  const v = c >= 100 ? c.toFixed(0) : c >= 0.01 || !c ? c.toFixed(2) : c.toFixed(4);
  return `${partial ? "≥ " : ""}US$ ${decimal(v)}`;
}

function isoDay(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function dayList(from, to) {
  const out = [];
  const d = new Date(`${from}T12:00:00`);
  const end = new Date(`${to}T12:00:00`);
  while (d <= end) { out.push(isoDay(d)); d.setDate(d.getDate() + 1); }
  return out;
}

function shortDay(day) {
  return `${day.slice(8, 10)}/${day.slice(5, 7)}`;
}

export class AgentsUsageView {
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.days = 30;
    this.until = options.until || null;  // end of the period (AAAA-MM-DD); without it, today
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.root.innerHTML = `<div class="loading"><span class="skeleton w-40"></span><span class="skeleton w-70"></span></div>`;
    this.watch = new RevisionWatch(() => this.load());
    this.load();
  }

  destroy() {
    if (this.watch) this.watch.stop();
    this.destroyed = true;
    if (this.retry) clearTimeout(this.retry);
  }

  range() {
    const end = this.until ? new Date(`${this.until}T12:00:00`) : new Date();
    const start = new Date(end);
    start.setDate(start.getDate() - (this.days - 1));
    return [isoDay(start), isoDay(end)];
  }

  async load() {
    if (this.loading) { this.pending = true; return; }  // period changed mid-load: reload at the end
    this.loading = true;
    const [from, to] = this.range();
    const q = `from=${from}&to=${to}`;
    try {
      const [day, project, model, session] = await Promise.all(["day", "project", "model", "session"]
        .map((g) => get(`/api/agents/usage?${q}&group=${g}`)));
      this.data = { day, project, model, session, from, to };
      // the lowest revision of the four reads: if the index changed midway, the next clock tick reloads
      this.watch.seen(Math.min(day.revision, project.revision, model.revision, session.revision));
      this.render();
      // before the first scan the index is still empty; polling pauses with the window hidden, so it rereads here
      if (!day.scanned && !this.retry && (this.retries = (this.retries || 0) + 1) <= 40) {
        this.retry = setTimeout(() => { this.retry = null; this.load(); }, 500);
      }
    } catch (err) {
      reportError(err);
    } finally {
      this.loading = false;
      if (this.pending && !this.destroyed) { this.pending = false; this.load(); }
    }
  }

  render() {
    const { day, project, model, session, from, to } = this.data;
    const tot = day.total;
    const csv = `/api/agents/usage.csv?from=${from}&to=${to}&group=session`;
    this.root.innerHTML = `
      <div class="page ag-page">
        <div class="ag-bar-row">
          <div class="segmented" role="tablist" aria-label="${t("Período")}">
            ${PERIODS.map((p) => `<button type="button" class="seg ${p === this.days ? "is-on" : ""}" data-days="${p}" role="tab" aria-selected="${p === this.days}">${t("{n} dias", { n: p })}</button>`).join("")}
          </div>
          <span class="dim hint">${t("{from} a {to}", { from: esc(shortDay(from)), to: esc(shortDay(to)) })}</span>
          <span class="spacer"></span>
          <button class="btn btn-sm" data-csv="${esc(csv)}">${icon("copy")}<span>${t("Copiar CSV")}</span></button>
        </div>
        <p class="us-note">${icon("info")}<span><b>${t("Estimativa no preço da API.")}</b> ${esc(day.estimate_note.replace(/^[^.]*API[^.]*\.\s*/, ""))}</span></p>
        <div class="ag-kpis us-kpis">
          <div class="ag-kpi"><span class="ag-kpi-v">${fmtTokens(tot.total_tokens)}</span><span class="ag-kpi-l">${t("tokens no período")}</span></div>
          <div class="ag-kpi"><span class="ag-kpi-v">${fmtCost(tot.cost, tot.cost_partial)}</span><span class="ag-kpi-l">${t("custo estimado no preço da API")}</span></div>
          <div class="ag-kpi"><span class="ag-kpi-v">${fmtTokens(tot.tokens.cache_read)}</span><span class="ag-kpi-l">${t("tokens lidos do cache")}</span></div>
          <div class="ag-kpi"><span class="ag-kpi-v">${tot.turns}</span><span class="ag-kpi-l">${t("turnos do modelo")}</span></div>
        </div>
        ${this.chart(day, from, to)}
        <div class="us-tables">
          ${this.table(t("Por projeto"), project.groups, (g) => esc(g.key))}
          ${this.table(t("Por modelo"), model.groups, (g) => `<span class="mono">${esc(g.key)}</span>`)}
        </div>
        ${this.table(t("Por sessão"), session.groups.slice(0, 50), (g) => `<button type="button" class="us-link" data-open="${esc(g.key)}">${agentMark(g.agent)}<span>${esc(g.project || t("sem projeto"))}</span><span class="dim mono">${esc(g.key.slice(0, 8))}</span></button>`, true)}
        ${tot.unpriced ? `<p class="dim hint">${t("{tokens} tokens de modelos sem preço conferido ficaram fora do custo. Edite {file} na pasta de dados para incluir.", { tokens: fmtTokens(tot.unpriced), file: `<span class="mono">precos.json</span>` })}</p>` : ""}
      </div>`;
  }

  chart(day, from, to) {
    const byDay = new Map(day.groups.map((g) => [g.key, g]));
    const days = dayList(from, to);
    const max = Math.max(1, ...days.map((d) => (byDay.get(d) || {}).total_tokens || 0));
    const present = AGENT_ORDER.filter((a) => day.groups.some((g) => g.agents[a]));
    const legend = present.map((a) => `<span class="us-leg">${agentMark(a)}<span class="us-sw us-${a}"></span>${esc(AGENT_NAMES[a] || a)}</span>`).join("");
    const label = Math.max(1, Math.ceil(days.length / 10));
    const cols = days.map((d, i) => {
      const g = byDay.get(d);
      const parts = present.map((a) => {
        const n = g && g.agents[a] ? g.agents[a].total_tokens : 0;
        return n ? `<span class="us-seg us-${a}" style="height:${(n / max) * 100}%"></span>` : "";
      }).join("");
      const tip = g ? t("{day}: {tokens} tokens, {cost}", { day: shortDay(d), tokens: fmtTokens(g.total_tokens), cost: fmtCost(g.cost, g.cost_partial) })
        + present.map((a) => g.agents[a] ? ` · ${AGENT_NAMES[a]} ${fmtTokens(g.agents[a].total_tokens)}` : "").join("")
        : t("{day}: sem uso", { day: shortDay(d) });
      return `<div class="us-col" title="${esc(tip)}" aria-label="${esc(tip)}"><div class="us-stack">${parts}</div>
        <span class="us-x">${i % label === 0 || i === days.length - 1 ? esc(shortDay(d)) : ""}</span></div>`;
    }).join("");
    return `<section class="panel us-chart-panel">
      <div class="panel-head">${icon("gauge")}<h2>${t("Tokens por dia")}</h2><span class="spacer"></span>${legend}</div>
      <div class="us-chart" role="img" aria-label="${t("Tokens por dia, separados por agente")}">
        ${max > 1 ? `<span class="us-max dim">${fmtTokens(max)}</span>` : ""}${cols}</div>
    </section>`;
  }

  table(title, groups, labelOf, session = false) {
    const rows = groups.length ? groups.map((g) => `<tr>
        <td>${labelOf(g)}</td><td class="num">${fmtTokens(g.total_tokens)}</td>
        <td class="num">${fmtTokens(g.tokens.cache_read)}</td><td class="num">${fmtCost(g.cost, g.cost_partial)}</td></tr>`).join("")
      : `<tr><td colspan="4" class="dim">${t("Sem uso no período.")}</td></tr>`;
    return `<section class="panel us-table${session ? " us-wide" : ""}">
      <div class="panel-head"><h2>${esc(title)}</h2></div>
      <table class="table"><thead><tr><th>${session ? t("Sessão") : t("Nome")}</th><th class="num">${t("Tokens")}</th><th class="num">${t("Cache lido")}</th><th class="num">${t("Custo estimado")}</th></tr></thead>
      <tbody>${rows}</tbody></table></section>`;
  }

  onClick(event) {
    const seg = event.target.closest("[data-days]");
    if (seg) { this.days = Number(seg.dataset.days); this.load(); return; }
    const open = event.target.closest("[data-open]");
    if (open) { this.options.navigate(`#/agentes/${open.dataset.open}`); return; }
    const csv = event.target.closest("[data-csv]");
    if (csv) this.download(csv.dataset.csv);
  }

  async download(path) {
    // the native window does not download files: the CSV goes to the clipboard (the route also serves the browser)
    try {
      const res = await fetch(path, { headers: { "X-Vulcan-Token": token } });
      if (!res.ok) throw new Error(`CSV: HTTP ${res.status}`);
      copy(await res.text(), t("CSV copiado"));
    } catch (err) {
      reportError(err);
    }
  }
}
