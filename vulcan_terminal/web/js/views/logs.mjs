// Aba Logs do site: storage/logs/laravel.log lido aos pedaços, com nível, busca e pausa; e atalhos que
// abrem os logs do Lerd (PHP-FPM, nginx, serviços) numa aba do terminal.

import { every, get, post } from "../api.mjs";
import { esc, icon, reportError } from "../dom.mjs";

const LIMIT = 2000;  // entradas na tela; as mais antigas saem
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
        <select class="select logs-level" aria-label="Nível">${LEVELS.map((l) => `<option value="${l}">${l || "Todos os níveis"}</option>`).join("")}</select>
        <input class="input logs-search" placeholder="Buscar no log" spellcheck="false" aria-label="Buscar no log">
        <button class="btn btn-sm" data-logs="pause" aria-pressed="false">${icon("stop")}<span>Pausar</span></button>
        <button class="btn btn-sm" data-logs="clear" title="Limpa a tela; o arquivo não muda">Limpar</button>
        <button class="btn btn-sm" data-logs="folder">${icon("folder")}<span>Abrir pasta</span></button>
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
    const data = await get(url);
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
      this.body.innerHTML = `<div class="empty-block"><h3>Sem laravel.log</h3>
        <p>Este site ainda não tem <code>${esc(this.path || "storage/logs/laravel.log")}</code>. Os logs do Lerd ficam nos botões acima.</p></div>`;
      return;
    }
    const stick = this.body.scrollHeight - this.body.scrollTop - this.body.clientHeight < 40;
    const shown = this.entries.filter((e) => (!this.level || e.level === this.level)
      && (!this.query || e.message.toLowerCase().includes(this.query)));
    this.body.innerHTML = shown.length ? shown.map((e) => `<div class="log-entry log-${TONE[e.level] || "info"}">
        <span class="log-ts">${esc(e.ts)}</span><span class="log-level">${esc(e.level)}</span><span class="log-channel dim">${esc(e.channel)}</span>
        <pre class="log-msg">${esc(e.message)}</pre></div>`).join("")
      : `<p class="dim logs-empty">Nada com esse filtro.</p>`;
    if (stick) this.body.scrollTop = this.body.scrollHeight;
  }

  async onClick(event) {
    const btn = event.target.closest("[data-logs], [data-lerd]");
    if (!btn) return;
    try {
      if (btn.dataset.logs === "pause") {
        this.paused = !this.paused;
        btn.setAttribute("aria-pressed", String(this.paused));
        btn.innerHTML = this.paused ? `${icon("play")}<span>Continuar</span>` : `${icon("stop")}<span>Pausar</span>`;
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
