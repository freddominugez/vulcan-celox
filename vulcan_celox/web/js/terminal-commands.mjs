// Per site: the project command menu and the chip with the PHP and Node versions in the tab bar.

import { del, get, post } from "./api.mjs";
import { $, esc, icon, reportError } from "./dom.mjs";
import { t } from "./i18n.mjs";
import { confirmDialog } from "./ai.mjs";

export class ProjectTools {
  constructor(workspace) {
    this.ws = workspace;
  }

  sitePath() {
    return `/api/sites/${encodeURIComponent(this.ws.options.site.name)}/commands`;
  }

  async loadCommands() {
    if (this.ws.options.scope !== "site" || !this.ws.options.site) return;
    try {
      this.commands = (await get(this.sitePath())).commands;
      this.ws.renderTabs();
      if (this.ws.mode === "terminal" && !this.ws.sessions().length) this.ws.renderContent();
    } catch {
      /* manual site without a folder, or server down: no button */
    }
  }

  async toggleCommands() {
    if (this.commandMenu && this.commandMenu.isConnected) return this.closeCommands();
    // the latest commands typed in the site's sessions come right below
    const recent = await get(`/api/sites/${encodeURIComponent(this.ws.options.site.name)}/recent`)
      .then((d) => d.commands).catch(() => []);
    this.closeCommands();  // the bar was redrawn with the menu open: clear the old listener
    const anchor = $(".cmd-btn", this.ws.strip);
    if (!anchor || !this.commands) return null;
    const menu = document.createElement("div");
    menu.className = "cmd-menu";
    menu.setAttribute("role", "menu");
    menu.innerHTML = this.commands.map((c) => `<div class="cmd-row">
        <button class="cmd-item" role="menuitem" data-action="quick" data-command="${esc(c.command)}" data-label="${esc(c.label)}">
          ${icon("play")}<span class="cmd-label">${esc(c.label)}</span><code>${esc(c.command)}</code></button>
        ${c.custom ? `<button class="icon-btn icon-btn-sm" data-action="del-cmd" data-command="${esc(c.command)}" aria-label="${t("Tirar {label}", { label: esc(c.label) })}" title="${t("Tirar da lista")}">${icon("x")}</button>` : ""}
      </div>`).join("") + `<button class="cmd-item cmd-add" role="menuitem" data-action="add-cmd">${icon("plus")}<span>${t("Adicionar comando…")}</span></button>`
      + (recent.length ? `<div class="cmd-group">${icon("history")}${t("Últimos comandos")}</div>` + recent.map((c) => `<div class="cmd-row">
        <button class="cmd-item" role="menuitem" data-action="quick" data-command="${esc(c.command)}" data-label="${esc(c.command.slice(0, 40))}"
          title="${t("Rodar de novo numa aba nova")}"><code class="cmd-recent">${esc(c.command)}</code></button>
        <button class="icon-btn icon-btn-sm" data-action="copy-cmd" data-command="${esc(c.command)}" aria-label="${t("Copiar")}" title="${t("Copiar")}">${icon("copy")}</button>
      </div>`).join("") : "");
    this.ws.strip.appendChild(menu);
    const box = anchor.getBoundingClientRect();
    const host = this.ws.strip.getBoundingClientRect();
    menu.style.left = `${Math.max(0, box.right - host.left - menu.offsetWidth)}px`;
    this.commandMenu = menu;
    this.offMenu = (e) => { if (!menu.contains(e.target) && !e.target.closest(".cmd-btn")) this.closeCommands(); };
    setTimeout(() => document.addEventListener("click", this.offMenu), 0);
    const first = menu.querySelector(".cmd-item");
    if (first) first.focus();
    return null;
  }

  closeCommands() {
    if (this.commandMenu) this.commandMenu.remove();
    this.commandMenu = null;
    if (this.offMenu) document.removeEventListener("click", this.offMenu);
    this.offMenu = null;
  }

  async addCommand() {
    this.closeCommands();
    let label = "";
    let command = "";
    const yes = await confirmDialog({
      title: t("Adicionar comando ao projeto"),
      body: `<label class="field-label" for="cmd-command">${t("Comando")}</label>
        <input id="cmd-command" class="input" data-command spellcheck="false" placeholder="php artisan queue:work">
        <label class="field-label" for="cmd-label">${t("Nome no menu (opcional)")}</label>
        <input id="cmd-label" class="input" data-label maxlength="60">`,
      confirmLabel: t("Adicionar"),
      onDecide: (answer, root) => {
        command = root.querySelector("[data-command]").value.trim();
        label = root.querySelector("[data-label]").value.trim();
      },
    });
    if (!yes || !command) return;
    try {
      this.commands = (await post(this.sitePath(), { label: label || command, command })).commands;
      this.ws.renderTabs();
    } catch (err) {
      reportError(err);
    }
  }

  async removeCommand(command) {
    this.closeCommands();
    try {
      this.commands = (await del(`${this.sitePath()}?command=${encodeURIComponent(command)}`)).commands;
      this.ws.renderTabs();
    } catch (err) {
      reportError(err);
    }
  }

  /** PHP and Node the backend uses for the site, with a warning if the tab does not go through the Lerd shims. */
  async loadRuntime() {
    if (this.ws.options.scope !== "site" || !this.ws.options.site) return;
    try {
      this.runtime = await get(`/api/sites/${encodeURIComponent(this.ws.options.site.name)}/runtime`);
      this.ws.renderTabs();
    } catch {
      /* backend missing or down: the bar has no chip */
    }
  }

  runtimeChip() {
    const r = this.runtime;
    if (!r || !(r.php || r.node)) return "";
    const warn = r.shim && !r.shim.ok ? r.shim.warning : "";
    const text = [r.php && `PHP ${r.php}`, r.node && `Node ${r.node}`].filter(Boolean).join(" · ");
    const tip = warn || (r.docroot ? t("Versões que o backend usa neste site; raiz {path}", { path: r.docroot }) : t("Versões que o backend usa neste site"));
    return `<span class="runtime-chip ${warn ? "is-warn" : ""}" title="${esc(tip)}">${warn ? icon("alert") : ""}${esc(text)}</span>`;
  }
}
