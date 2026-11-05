// Site Logs tab: storage/logs/laravel.log read in chunks, with level, search and pause; and shortcuts that
// open the Lerd logs (PHP-FPM, nginx, services) in a terminal tab.

import { every, get, post } from "../api.mjs";
import { esc, icon, reportError } from "../dom.mjs";
import { t } from "../i18n.mjs";

const LIMIT = 2000;  // entries on screen; the oldest drop off
const LEVELS = ["", "ERROR", "WARNING", "INFO", "DEBUG"];
const TONE = { EMERGENCY: "err", ALERT: "err", CRITICAL: "err", ERROR: "err", WARNING: "warn", NOTICE: "warn", INFO: "info", DEBUG: "dim" };

export class LogsView {
  constructor(root, options) {
    this.root = root;
    this.site = options.site;
    this.onTerminal = options.onTerminal || (() => {});
    this.entries = [];
    this.offset = null;
    this.level = "";
    this.query = "";
    this.paused = false;
    this.root.innerHTML = `<div class="logs">
      <div class="logs-bar">
        <select class="select logs-level" aria-label="${t("Nível")}">${LEVELS.map((l) => `<option value="${l}">${l || t("Todos os níveis")}</option>`).join("")}</select>
        <input class="input logs-search" placeholder="${t("Buscar no log")}" spellcheck="false" aria-label="${t("Buscar no log")}">
        <button class="btn btn-sm" data-logs="pause" aria-pressed="false">${icon("stop")}<span>${t("Pausar")}</span></button>
        <button class="btn btn-sm" data-logs="clear" title="${t("Limpa a tela; o arquivo não muda")}">${t("Limpar")}</button>
        <button class="btn btn-sm" data-logs="folder">${icon("folder")}<span>${t("Abrir pasta")}</span></button>
        <span class="spacer"></span>
        <span class="dim logs-lerd">Lerd:</span>
        <button class="btn btn-sm" data-lerd="php" title="lerd logs -f">PHP-FPM</button>
        <button class="btn btn-sm" data-lerd="nginx" title="lerd logs nginx -f">nginx</button>
      </div>
      <div class="logs-body" role="log" aria-live="polite"></div>
    </div>`;
    this.body = this.root.querySelector(".logs-body");
    this.root.querySelector(".logs-level").addEventListener("change", (e) => { this.level = e.target.value; this.draw(); });
    this.root.querySelector(".logs-search").addEventListener("input", (e) => { this.query = e.target.value.trim().toLowerCase(); this.draw(); });
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.stopTimer = every(2000, () => this.load());
    this.load();
  }

  async load() {
    if (this.paused) return;
    const url = `/api/sites/${encodeURIComponent(this.site.name)}/log${this.offset === null ? "" : `?offset=${this.offset}`}`;
    let data;
    try {
      data = await get(url);
    } catch (err) {
      // the site left the list while the tab was open (removed, or the environment stopped): say so, and keep asking
      if (err.status === 404) {
        this.offset = null;
        this.entries = [];
        const title = t("Site “{site}” não encontrado", { site: esc(this.site.name) });
        const note = t("O site saiu da lista do ambiente. Os logs voltam quando ele voltar.");
        this.body.innerHTML = `<div class="empty-block"><h3>${title}</h3><p>${note}</p></div>`;
      }
      return;
    }
    this.path = data.path;
    this.folder = data.folder;
    this.exists = data.exists;
    if (data.reset) this.entries = [];
    this.offset = data.offset;
    if (data.entries.length || this.entries.length === 0) {
      this.entries = this.entries.concat(data.entries).slice(-LIMIT);
      this.draw();
    }
  }

  draw() {
    if (!this.exists) {
      this.body.innerHTML = `<div class="empty-block"><h3>${t("Sem laravel.log")}</h3>
        <p>${t("Este site ainda não tem <code>{path}</code>. Os logs do Lerd ficam nos botões acima.", { path: esc(this.path || "storage/logs/laravel.log") })}</p></div>`;
      return;
    }
    const stick = this.body.scrollHeight - this.body.scrollTop - this.body.clientHeight < 40;
    const shown = this.entries.filter((e) => (!this.level || e.level === this.level)
      && (!this.query || e.message.toLowerCase().includes(this.query)));
    this.body.innerHTML = shown.length ? shown.map((e) => `<div class="log-entry log-${TONE[e.level] || "info"}">
        <span class="log-ts">${esc(e.ts)}</span><span class="log-level">${esc(e.level)}</span><span class="log-channel dim">${esc(e.channel)}</span>
        <pre class="log-msg">${esc(e.message)}</pre></div>`).join("")
      : `<p class="dim logs-empty">${t("Nada com esse filtro.")}</p>`;
    if (stick) this.body.scrollTop = this.body.scrollHeight;
  }

  async onClick(event) {
    const btn = event.target.closest("[data-logs], [data-lerd]");
    if (!btn) return;
    try {
      if (btn.dataset.logs === "pause") {
        this.paused = !this.paused;
        btn.setAttribute("aria-pressed", String(this.paused));
        btn.innerHTML = this.paused ? `${icon("play")}<span>${t("Continuar")}</span>` : `${icon("stop")}<span>${t("Pausar")}</span>`;
        if (!this.paused) this.load();
      }
      if (btn.dataset.logs === "clear") {
        this.entries = [];
        this.draw();
      }
      if (btn.dataset.logs === "folder" && this.folder) await post("/api/open", { kind: "finder", target: this.folder });
      if (btn.dataset.lerd) {
        const tab = await post(`/api/sites/${encodeURIComponent(this.site.name)}/lerd-logs/${btn.dataset.lerd}`);
        await this.onTerminal(tab.id);
      }
    } catch (err) {
      reportError(err);
    }
  }

  destroy() {
    this.stopTimer();
  }
}
