// Workspace: sessions with Terminal, Tarefas, Post-its and Tags tabs, and the split into two panels.

import { get, post } from "./api.mjs";
import { $, debounce, icon, reportError, toast } from "./dom.mjs";
import { t } from "./i18n.mjs";
import { documentSession, onJobsChange } from "./ai.mjs";
import { askFolder, suggestedFolder } from "./folder-dialog.mjs";
import { PromptBar } from "./prompt-bar.mjs";
import { copy } from "./agents-ui.mjs";
import { clearTab } from "./attention-state.mjs";
import { loadThemes, themes as themeState } from "./themes.mjs";
import { terminals } from "./terminal-pool.mjs";
import { TerminalSearch } from "./terminal-search.mjs";
import { ProjectTools } from "./terminal-commands.mjs";
import { onTabKey, renameTabOnDblClick, renderTabs } from "./terminal-tabs.mjs";
import { destroyChild, renderContent } from "./terminal-content.mjs";

const MODES = ["terminal", "tasks", "notes", "tags", "harness", "logs", "debug"];

export class TerminalWorkspace {
  /**
   * @param {HTMLElement} root
   * @param {{site?: object|null, scope: "site"|"all", mode?: string, sessionId?: string,
   *          sites?: object[], onChange?: Function, onSelect?: Function}} options
   */
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.mode = MODES.includes(options.mode) ? options.mode : "terminal";
    this.activeId = options.sessionId || null;
    this.splitId = null;
    this.records = new Map();
    this.closed = [];
    this.loaded = false;
    this.requestedId = options.sessionId || null; // session requested by the route, maybe closed (history)
    this.child = null;
    this.childKey = "";
    this.focus = options.focus || null;
    this.memoryView = "memory";
    this.root.innerHTML = `<div class="term-workspace"><div class="tabstrip" role="tablist"></div>
      <div class="term-search" hidden>${icon("search")}
        <input class="term-search-input" placeholder="${t("Buscar no terminal")}" aria-label="${t("Buscar no terminal")}" spellcheck="false" autocomplete="off">
        <span class="term-search-count" aria-live="polite"></span>
        <button class="icon-btn icon-btn-sm" data-search="prev" aria-label="${t("Anterior")}" title="${t("Anterior (⇧Enter)")}">${icon("chevron-up")}</button>
        <button class="icon-btn icon-btn-sm" data-search="next" aria-label="${t("Próximo")}" title="${t("Próximo (Enter)")}">${icon("chevron-down")}</button>
        <button class="icon-btn icon-btn-sm" data-search="close" aria-label="${t("Fechar busca")}" title="${t("Fechar (Esc)")}">${icon("x")}</button>
      </div>
      <div class="prompt-bar" hidden></div><div class="ws-body"></div></div>`;
    this.search = new TerminalSearch(this, $(".term-search", this.root));
    this.project = new ProjectTools(this);
    this.strip = $(".tabstrip", this.root);
    this.body = $(".ws-body", this.root);
    this.promptBar = new PromptBar($(".prompt-bar", this.root));
    this.resizeObserver = new ResizeObserver(() => this.visible().forEach((s) => s.resizeSoon()));
    this.loadSoon = debounce(() => this.loadSessions(), 250);
    this.unsubscribe = terminals.subscribe(() => {
      this.render();
      this.loadSoon();
    });
    // renaming or deleting from the sidebar updates tabs, history chip and content
    this.onSessionsChanged = async () => {
      await this.loadSessions();
      this.childKey = "";
      this.render();
    };
    window.addEventListener("vulcan-sessions-changed", this.onSessionsChanged);
    this.offJobs = onJobsChange(async () => {
      await this.loadSessions();
      if (this.mode === "terminal" && this.activeId && !this.isLive(this.activeId)) this.renderContent();
    });
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.root.addEventListener("dblclick", (e) => this.onDblClick(e));
    this.root.addEventListener("keydown", (e) => this.onTabKey(e));
    this.render();
    if (this.activeId && !this.isLive(this.activeId)) terminals.sync();
    this.loadSessions();
    this.project.loadRuntime();
    this.project.loadCommands();
  }

  // ── dados ──────────────────────────────────────────────────────────────
  siteParam() {
    if (this.options.scope === "all") return "*";
    return this.options.site ? this.options.site.name : "";
  }

  sessions() {
    return this.options.scope === "all" ? terminals.list() : terminals.list(this.options.site ? this.options.site.name : undefined);
  }

  isLive(id) {
    return Boolean(id && terminals.get(id));
  }

  visible() {
    if (this.mode !== "terminal") return [];
    return [this.activeId, this.splitId]
      .filter((id) => this.isLive(id) && !terminals.popped.has(id))
      .map((id) => terminals.get(id));
  }

  async loadSessions() {
    try {
      const data = await get(`/api/sessions?site=${encodeURIComponent(this.siteParam())}`);
      this.records = new Map([...data.open, ...data.closed].map((r) => [r.id, r]));
      this.closed = data.closed;
      const first = !this.loaded;
      this.loaded = true;
      if (first) return this.render();
      this.renderTabs();
      if (this.mode === "terminal" && this.activeId && !this.isLive(this.activeId)) this.renderContent();
    } catch (err) {
      reportError(err);
    }
  }

  /** Tabs = open terminals only. Closed sessions open from the Histórico folder, without becoming a tab. */
  tabIds() {
    return this.sessions().map((s) => s.info.id);
  }

  isHistory(id = this.activeId) {
    const record = this.records.get(id);
    return Boolean(id && !this.isLive(id) && record && !record.open);
  }

  lastLiveId() {
    const live = this.sessions();
    return live.length ? live[live.length - 1].info.id : null;
  }

  activeSite() {
    if (this.options.site) return this.options.site.name;
    const record = this.records.get(this.activeId);
    const live = terminals.get(this.activeId);
    return (live && live.info.site) || (record && record.site) || "";
  }

  // ── actions ────────────────────────────────────────────────────────────
  async newTerminal(command = null, title = null, { ask = false } = {}) {
    const site = this.options.scope === "site" ? this.options.site : null;
    let cwd = null;
    let theme = null;
    let agent = null;
    // a plain terminal asks for the folder, already with the next theme; with "não perguntar" it opens directly;
    // quick commands (Tinker, git status) run in the site folder, with no theme
    if (!command) {
      await loadThemes(true);
      const prefs = themeState.newTerminal || {};
      if (prefs.skip_folder && !ask) {
        cwd = await suggestedFolder(site);
        theme = "auto";
        agent = prefs.agent;
      } else {
        const choice = await askFolder({ suggested: site ? site.path : "", site: site ? site.name : "" });
        if (!choice) return null;
        ({ cwd, theme, agent } = choice);
        title = choice.title || title;
      }
    }
    try {
      const session = await terminals.create({ site: site ? site.name : null, cwd, command, title, theme, agent });
      loadThemes(true);  // next in the rotation and tabs in use changed
      this.activeId = session.info.id;
      this.setMode("terminal");
      session.focus();
      return session;
    } catch (err) {
      reportError(err);
      return null;
    }
  }

  /** Shows a session (open or closed) in a tab, with one item highlighted. */
  reveal(id, mode, focus = null) {
    if (MODES.includes(mode)) this.mode = mode;
    if (id) {
      this.activeId = id;
      if (!this.isLive(id)) {
        this.requestedId = id;
        terminals.sync();  // created by the server a moment ago (installer, resumed session): the pool does not know it yet
      }
      if (this.splitId === id) this.splitId = null;
    }
    this.focus = focus || null;
    this.childKey = "";
    this.render();
    if (!this.loaded || (id && !this.records.has(id))) this.loadSessions();
  }

  setMode(mode) {
    if (!MODES.includes(mode)) return;
    this.mode = mode;
    if (mode !== "terminal") this.splitId = null;
    this.render();
  }

  popoutActive() {
    if (this.isLive(this.activeId)) terminals.popout(this.activeId);
  }

  select(id) {
    this.activeId = id;
    clearTab(id);
    if (this.splitId === id) this.splitId = null;
    this.render();
    if (this.options.onSelect) this.options.onSelect(id);
    const s = terminals.get(id);
    if (s && this.mode === "terminal" && !terminals.popped.has(id)) s.focus();
  }

  async closeTerminal(id, force = false) {
    const live = terminals.get(id);
    if (!live) return;
    try {
      if (!force) {
        // the check only protects; if it fails, closing is still possible
        const busy = await get(`/api/terminals/${id}/busy`).catch(() => ({ busy: false, processes: [] }));
        if (busy.long_running && live.alive) {
          // says what it stops, instead of the generic running-process warning
          toast(t("Fechar a aba para “{command}”.", { command: busy.command }), {
            kind: "error", timeout: 8000,
            action: { label: t("Fechar e parar"), run: () => this.closeTerminal(id, true) },
          });
          return;
        }
        if (busy.busy) {
          toast(t("“{title}” ainda está rodando {processes}.", { title: live.info.title, processes: busy.processes.slice(0, 2).join(", ") }), {
            kind: "error", timeout: 8000,
            action: { label: t("Fechar mesmo assim"), run: () => this.closeTerminal(id, true) },
          });
          return;
        }
      }
      const result = await terminals.close(id);
      // the tab goes away; the session stays in the Histórico folder of the sidebar
      if (this.activeId === id) this.activeId = this.lastLiveId();
      if (this.splitId === id) this.splitId = null;
      await this.loadSessions();
      this.render();
      if (result && result.memory_file) {
        const name = result.memory_file.split("/").slice(-2).join("/");
        toast(t("Sessão guardada no Histórico · memória em {name}", { name }), {
          kind: "ok", timeout: 7000,
          action: { label: t("Abrir"), run: () => post("/api/open", { kind: "file", target: result.memory_file }).catch(reportError) },
        });
      }
    } catch (err) {
      reportError(err);
    }
  }

  onClick(event) {
    const target = event.target.closest("[data-action]");
    if (!target || !this.root.contains(target)) return;
    // tasks, sticky notes and tags handle their own buttons; without this "Novo post-it" also opened a terminal
    if (target.closest(".tasks, .notes, .session-tags")) return;
    const { action, id } = target.dataset;
    if (action === "select") this.select(id);
    if (action === "close") {
      event.stopPropagation();
      this.closeTerminal(id);
    }
    if (action === "new") this.newTerminal();
    if (action === "find") this.openSearch();
    if (action === "copy-output") this.search.copyOutput();
    if (action === "leave-history") {
      this.activeId = this.lastLiveId();
      this.requestedId = null;
      this.render();
      if (this.options.onSelect) this.options.onSelect(this.activeId);
    }
    if (action === "quick") {
      this.project.closeCommands();
      this.newTerminal(target.dataset.command, target.dataset.label);
    }
    if (action === "commands") this.project.toggleCommands();
    if (action === "add-cmd") this.project.addCommand();
    if (action === "copy-cmd") {
      event.stopPropagation();
      copy(target.dataset.command, t("Comando copiado."));
    }
    if (action === "del-cmd") {
      event.stopPropagation();
      this.project.removeCommand(target.dataset.command);
    }
    if (action === "open-memory") {
      const record = this.records.get(id);
      const file = record && (target.dataset.file === "doc" ? record.memory_file.replace(/\.md$/, ".doc.md") : record.memory_file);
      if (file) post("/api/open", { kind: "file", target: file }).catch(reportError);
    }
    if (action === "memory-view") {
      this.memoryView = target.dataset.view;
      this.renderContent();
    }
    if (action === "document") {
      const live = terminals.get(id);
      const record = this.records.get(id);
      documentSession(id, live ? live.info.title : record ? record.title : id);
    }
    if (action === "split") {
      const others = this.sessions().filter((s) => s.info.id !== this.activeId && !terminals.popped.has(s.info.id));
      if (this.splitId) this.splitId = null;
      else if (others.length && this.isLive(this.activeId)) this.splitId = others[others.length - 1].info.id;
      else {
        this.newTerminal().then((s) => {
          if (!s) return;
          const first = this.sessions().find((x) => x.info.id !== s.info.id);
          if (first) {
            this.splitId = s.info.id;
            this.activeId = first.info.id;
            this.render();
          }
        });
        return;
      }
      this.render();
    }
    if (action === "popout") this.popoutActive();
    if (action === "focus-popout") terminals.focusPopout(id);
  }

  focusPane(id) {
    if (!this.splitId || this.activeId === id) return;
    this.splitId = this.activeId;
    this.activeId = id;
    this.strip.querySelectorAll(".tab").forEach((tab) => {
      tab.classList.toggle("is-active", tab.dataset.id === this.activeId);
      tab.classList.toggle("is-shown", tab.dataset.id === this.splitId);
    });
    this.body.querySelectorAll(".pane").forEach((pane) => pane.classList.toggle("is-focused", pane.dataset.session === id));
    if (this.options.onSelect) this.options.onSelect(id);
  }

  onTabKey(event) {
    onTabKey(this, event);
  }

  onDblClick(event) {
    renameTabOnDblClick(this, event);
  }

  openSearch() {
    return this.search.open();
  }

  // ── desenho ────────────────────────────────────────────────────────────
  render() {
    const ids = this.tabIds();
    // before the first load the session requested by the route may not have a record yet
    const waiting = !this.loaded && this.activeId && this.activeId === this.requestedId;
    if (!waiting && !ids.includes(this.activeId) && !this.isHistory()) this.activeId = this.lastLiveId();
    if (this.splitId && (!this.isLive(this.splitId) || this.mode !== "terminal")) this.splitId = null;
    this.renderTabs();
    this.renderContent();
  }

  renderTabs() {
    renderTabs(this);
  }

  renderContent() {
    // the dark scope is for the terminal: tasks, notes, harness and logs follow the app's theme
    this.body.classList.toggle("is-terminal", this.mode === "terminal");
    return renderContent(this);
  }

  destroy() {
    this.project.closeCommands();  // removes the listener of the command menu from the document
    this.search.dispose();
    this.unsubscribe();
    this.offJobs();
    this.promptBar.destroy();
    window.removeEventListener("vulcan-sessions-changed", this.onSessionsChanged);
    this.resizeObserver.disconnect();
    destroyChild(this);
    // sessions stay in the pool: leaving the screen does not end terminals
    this.sessions().forEach((s) => s.el.remove());
  }
}
