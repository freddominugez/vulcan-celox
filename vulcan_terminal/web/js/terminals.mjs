// Terminais: pool de sessões xterm conectadas por WebSocket e o espaço de trabalho com abas e divisão.

import { del, get, isMac, isNative, native, patch, post, wsUrl } from "./api.mjs";
import { $, $$, debounce, esc, icon, reportError, shortPath, toast } from "./dom.mjs";
import { confirmDialog, documentSession, onJobsChange } from "./ai.mjs";
import { askFolder, suggestedFolder } from "./folder-dialog.mjs";
import { renderMarkdown } from "./markdown.mjs";
import { PromptBar } from "./prompt-bar.mjs";
import { copy } from "./agents-ui.mjs";
import { loadThemes, themes as themeState, xtermTheme } from "./themes.mjs";
import { DebugView } from "./views/debug.mjs";
import { LogsView } from "./views/logs.mjs";
import { HarnessView } from "./views/harness.mjs";
import { NotesView } from "./views/notes.mjs";
import { SessionTagsView } from "./views/session-tags.mjs";
import { TasksView } from "./views/tasks.mjs";

const THEME = {
  background: "#0f0f11",
  foreground: "#e6e6e9",
  cursor: "#ff6a4a",
  cursorAccent: "#0f0f11",
  selectionBackground: "rgba(255, 106, 74, 0.28)",
  black: "#1f1f23", red: "#ff6b5e", green: "#4fd08a", yellow: "#f2c14e",
  blue: "#6aa8ff", magenta: "#d38cff", cyan: "#4fcfd6", white: "#d4d4da",
  brightBlack: "#6b6b75", brightRed: "#ff8a7f", brightGreen: "#74e0a5", brightYellow: "#f7d67c",
  brightBlue: "#92c0ff", brightMagenta: "#e2adff", brightCyan: "#7fe0e6", brightWhite: "#f5f5f7",
};

window.addEventListener("vulcan-themes-loaded", () => {
  terminals.list().forEach((s) => {
    const palette = xtermTheme(s.info.theme);
    if (palette) s.term.options.theme = palette;
  });
});
loadThemes();

/** Instância de um addon vendorizado, ou null se o arquivo não carregou (o terminal funciona sem ele). */
function addon(name) {
  const mod = window[name];
  try {
    return mod && mod[name] ? new mod[name]() : null;
  } catch {
    return null;
  }
}

const SEARCH_DECORATIONS = {
  matchBackground: "#6b5420", matchBorder: "#f2c14e", matchOverviewRuler: "#f2c14e",
  activeMatchBackground: "#ff6a4a", activeMatchBorder: "#ffb4a3", activeMatchColorOverviewRuler: "#ff6a4a",
};
// sequências de controle que o serialize grava para restaurar cores e cursor; para copiar texto, saem
const ANSI = /\x1b\[[0-9;?]*[ -\/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b[()][0-9A-Za-z]|\x1b[=>78]/g;

const decoder = new TextDecoder();
const encoder = new TextEncoder();

class Session {
  constructor(info, hooks) {
    this.info = info;
    this.hooks = hooks;
    this.el = document.createElement("div");
    this.el.className = "xterm-host";
    this.term = new window.Terminal({
      fontFamily: 'ui-monospace, "SF Mono", SFMono-Regular, Menlo, monospace',
      fontSize: 13,
      lineHeight: 1.22,
      cursorBlink: true,
      cursorStyle: "bar",
      allowProposedApi: true,  // a API de unicode (addon-unicode11) é marcada como proposta no xterm 6
      scrollback: 10000,
      macOptionIsMeta: true,
      theme: xtermTheme(info.theme) || THEME,
    });
    this.fit = new window.FitAddon.FitAddon();
    this.term.loadAddon(this.fit);
    this.term.loadAddon(new window.WebLinksAddon.WebLinksAddon((_event, uri) => hooks.openUrl(uri)));
    // vt-19 C3: busca com contagem, largura certa de emoji e acentos, e cópia fiel da saída
    this.search = addon("SearchAddon");
    this.serializer = addon("SerializeAddon");
    const unicode = addon("Unicode11Addon");
    for (const a of [this.search, this.serializer, unicode]) if (a) this.term.loadAddon(a);
    if (unicode) this.term.unicode.activeVersion = "11";
    this.term.attachCustomKeyEventHandler((event) => {
      // atalhos com Cmd ficam com o app (menus nativos e paleta)
      if (event.metaKey && !["c", "v", "a"].includes(event.key.toLowerCase())) return false;
      return true;
    });
    this.opened = false;
    this.alive = info.alive;
    this.ws = null;
    this.retry = 0;
    this.term.onData((data) => {
      if (this.disconnected) {
        if (data.includes("\r")) this.reconnect();  // Enter na aba desconectada tenta de novo (vt-20 C8)
        return;
      }
      this.send(encoder.encode(data));
    });
    this.term.onBinary((data) => this.send(Uint8Array.from(data, (c) => c.charCodeAt(0))));
    this.term.onTitleChange((title) => hooks.onTitle(this, title));
  }

  mount(container) {
    container.appendChild(this.el);
    if (!this.opened) {
      this.term.open(this.el);
      this.opened = true;
      this.useWebgl();
      this.connect();
    }
    this.resizeSoon();
  }

  /** Desenho por WebGL quando o contexto existe; se falhar ou for perdido, volta ao desenho padrão. */
  useWebgl() {
    const Webgl = window.WebglAddon && window.WebglAddon.WebglAddon;
    if (!Webgl) return;
    try {
      const webgl = new Webgl();
      webgl.onContextLoss(() => webgl.dispose());
      this.term.loadAddon(webgl);
      this.renderer = "webgl";
    } catch {
      this.renderer = "dom";  // sem WebGL: o xterm segue com o desenho padrão
    }
  }

  connect() {
    if (this.ws) return;
    this.term.reset();
    const ws = new WebSocket(wsUrl(`/ws/terminals/${this.info.id}`));
    ws.binaryType = "arraybuffer";
    ws.onopen = () => {
      this.retry = 0;
      this.sendResize();
    };
    ws.onmessage = (event) => {
      if (typeof event.data === "string") {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "exit") {
            this.alive = false;
            this.term.write(`\r\n\x1b[2m[processo encerrado${msg.code != null ? ` com código ${msg.code}` : ""}]\x1b[0m\r\n`);
            this.hooks.onExit(this);
          }
        } catch {
          /* mensagem de controle desconhecida */
        }
        return;
      }
      this.term.write(new Uint8Array(event.data));
    };
    ws.onclose = () => {
      this.ws = null;
      if (this.alive && !this.disposed && this.retry < 5) {
        this.retry += 1;
        setTimeout(() => this.connect(), 400 * this.retry);
      } else if (this.alive && !this.disposed) {
        // desistiu de reconectar sozinho: a aba diz o que houve em vez de ficar muda (vt-20 C8)
        this.disconnected = true;
        this.term.write("\r\n\x1b[33m[conexão com o terminal perdida. Pressione Enter para reconectar.]\x1b[0m\r\n");
        this.hooks.onExit(this);
      }
    };
    this.ws = ws;
  }

  reconnect() {
    this.disconnected = false;
    this.retry = 0;
    this.hooks.onExit(this);
    this.connect();
  }

  send(bytes) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(bytes);
  }

  sendResize() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "resize", rows: this.term.rows, cols: this.term.cols }));
    }
  }

  resizeSoon() {
    requestAnimationFrame(() => {
      if (!this.el.isConnected || this.el.clientWidth < 20) return;
      try {
        this.fit.fit();
        // reanexar o elemento no DOM não repinta as linhas do renderer; força o redesenho
        this.term.refresh(0, this.term.rows - 1);
      } catch {
        return;
      }
      this.sendResize();
    });
  }

  focus() {
    this.term.focus();
  }

  dispose() {
    this.disposed = true;
    if (this.ws) this.ws.close();
    this.term.dispose();
    this.el.remove();
  }
}

// ── pool global ─────────────────────────────────────────────────────────────
export const terminals = {
  sessions: new Map(),
  order: [],
  popped: new Set(),
  listeners: new Set(),
  hooks: {
    openUrl: (uri) => post("/api/open", { kind: "url", target: uri }).catch(reportError),
    onTitle: () => {},
    onExit: () => terminals.emit(),
  },

  emit() {
    this.listeners.forEach((fn) => fn());
  },

  subscribe(fn) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  },

  async sync() {
    const data = await get("/api/terminals");
    const ids = new Set(data.terminals.map((t) => t.id));
    for (const info of data.terminals) {
      const current = this.sessions.get(info.id);
      if (current) {
        current.info = info;
      } else {
        this.sessions.set(info.id, new Session(info, this.hooks));
        this.order.push(info.id);
      }
    }
    for (const id of [...this.sessions.keys()]) {
      if (!ids.has(id)) this.drop(id);
    }
    this.emit();
    return this.list();
  },

  list(site) {
    return this.order
      .map((id) => this.sessions.get(id))
      .filter((s) => s && (site === undefined || (s.info.site || "") === (site || "")));
  },

  get(id) {
    return this.sessions.get(id);
  },

  async create({ site = null, cwd = null, command = null, title = null, theme = null, agent = null } = {}) {
    const info = await post("/api/terminals", { site, cwd, command, title, theme, agent, rows: 30, cols: 110 });
    const session = new Session(info, this.hooks);
    this.sessions.set(info.id, session);
    this.order.push(info.id);
    this.emit();
    return session;
  },

  async close(id) {
    let result = null;
    try {
      result = await del(`/api/terminals/${id}`);
    } catch (err) {
      if (err.status !== 404) throw err;
    }
    this.drop(id);
    this.emit();
    return result;
  },

  drop(id) {
    const session = this.sessions.get(id);
    if (session) session.dispose();
    this.sessions.delete(id);
    this.order = this.order.filter((x) => x !== id);
    this.popped.delete(id);
  },

  async rename(id, title) {
    const info = await patch(`/api/terminals/${id}`, { title });
    const session = this.sessions.get(id);
    if (session) session.info = info;
    this.emit();
  },

  popout(id) {
    const session = this.sessions.get(id);
    if (!session) return;
    const title = `${session.info.title} · Vulcan Terminal`;
    if (!native({ type: "popout", id, title })) {
      window.open(`${location.pathname}#/popout/${id}`, `vulcan-${id}`, "width=900,height=560");
    }
    this.popped.add(id);
    if (session.el.isConnected) session.el.remove();
    this.emit();
  },

  focusPopout(id) {
    native({ type: "focusPopout", id });
  },
};

window.addEventListener("vulcan-popout-closed", (event) => {
  terminals.popped.delete(event.detail);
  terminals.emit();
});

const QUICK = [
  { label: "git status", command: "git status -sb" },
  { label: "composer install", command: "composer install", when: (s) => s && s.has_composer },
  { label: "php artisan about", command: "php artisan about", when: (s) => s && s.has_artisan },
  { label: "npm run dev", command: "npm run dev", when: (s) => s && s.has_package_json },
];

// ── espaço de trabalho: sessões com abas Terminal, Tarefas, Post-its e Tags ─
const MODES = ["terminal", "tasks", "notes", "tags", "harness", "logs", "debug"];

function formatStamp(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

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
    this.requestedId = options.sessionId || null; // sessão pedida pela rota, talvez encerrada (histórico)
    this.child = null;
    this.childKey = "";
    this.focus = options.focus || null;
    this.memoryView = "memory";
    this.root.innerHTML = `<div class="term-workspace"><div class="tabstrip" role="tablist"></div>
      <div class="term-search" hidden>${icon("search")}
        <input class="term-search-input" placeholder="Buscar no terminal" aria-label="Buscar no terminal" spellcheck="false" autocomplete="off">
        <span class="term-search-count" aria-live="polite"></span>
        <button class="icon-btn icon-btn-sm" data-search="prev" aria-label="Anterior" title="Anterior (⇧Enter)">${icon("chevron-up")}</button>
        <button class="icon-btn icon-btn-sm" data-search="next" aria-label="Próximo" title="Próximo (Enter)">${icon("chevron-down")}</button>
        <button class="icon-btn icon-btn-sm" data-search="close" aria-label="Fechar busca" title="Fechar (Esc)">${icon("x")}</button>
      </div>
      <div class="prompt-bar" hidden></div><div class="ws-body"></div></div>`;
    this.searchBar = $(".term-search", this.root);
    this.bindSearch();
    this.strip = $(".tabstrip", this.root);
    this.body = $(".ws-body", this.root);
    this.promptBar = new PromptBar($(".prompt-bar", this.root));
    this.resizeObserver = new ResizeObserver(() => this.visible().forEach((s) => s.resizeSoon()));
    this.loadSoon = debounce(() => this.loadSessions(), 250);
    this.unsubscribe = terminals.subscribe(() => {
      this.render();
      this.loadSoon();
    });
    // renomear ou apagar pela barra lateral atualiza abas, chip do histórico e conteúdo
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
    this.loadSessions();
    this.loadRuntime();
    this.loadCommands();
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

  /** Abas = só terminais abertos. Sessões encerradas abrem pela pasta Histórico, sem virar aba. */
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

  // ── ações ──────────────────────────────────────────────────────────────
  async newTerminal(command = null, title = null, { ask = false } = {}) {
    const site = this.options.scope === "site" ? this.options.site : null;
    let cwd = null;
    let theme = null;
    let agent = null;
    // terminal comum pergunta a pasta (vt-11), já com o próximo tema; com "não perguntar" abre direto (D-008);
    // comandos rápidos (Tinker, git status) rodam na pasta do site, sem tema
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
      loadThemes(true);  // próximo da rotação e abas em uso mudaram
      this.activeId = session.info.id;
      this.setMode("terminal");
      session.focus();
      return session;
    } catch (err) {
      reportError(err);
      return null;
    }
  }

  /** Mostra uma sessão (aberta ou encerrada) numa aba, com um item em destaque. */
  reveal(id, mode, focus = null) {
    if (MODES.includes(mode)) this.mode = mode;
    if (id) {
      this.activeId = id;
      if (!this.isLive(id)) this.requestedId = id;
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
        // a checagem só protege; se falhar, fechar continua possível
        const busy = await get(`/api/terminals/${id}/busy`).catch(() => ({ busy: false, processes: [] }));
        if (busy.long_running && live.alive) {
          // vt-04 C3: diz o que para, em vez do aviso genérico de processo rodando
          toast(`Fechar a aba para “${busy.command}”.`, {
            kind: "error", timeout: 8000,
            action: { label: "Fechar e parar", run: () => this.closeTerminal(id, true) },
          });
          return;
        }
        if (busy.busy) {
          toast(`“${live.info.title}” ainda está rodando ${busy.processes.slice(0, 2).join(", ")}.`, {
            kind: "error", timeout: 8000,
            action: { label: "Fechar mesmo assim", run: () => this.closeTerminal(id, true) },
          });
          return;
        }
      }
      const result = await terminals.close(id);
      // a aba some; a sessão fica na pasta Histórico da barra lateral
      if (this.activeId === id) this.activeId = this.lastLiveId();
      if (this.splitId === id) this.splitId = null;
      await this.loadSessions();
      this.render();
      if (result && result.memory_file) {
        const name = result.memory_file.split("/").slice(-2).join("/");
        toast(`Sessão guardada no Histórico · memória em ${name}`, {
          kind: "ok", timeout: 7000,
          action: { label: "Abrir", run: () => post("/api/open", { kind: "file", target: result.memory_file }).catch(reportError) },
        });
      }
    } catch (err) {
      reportError(err);
    }
  }

  /** Abas pelo teclado (vt-20 C8): setas trocam de aba, Enter ou espaço abrem a focada. */
  onTabKey(event) {
    const tab = event.target.closest && event.target.closest(".tab[role=tab]");
    if (!tab || event.target.closest(".tab-close")) return;
    const tabs = [...tab.parentElement.querySelectorAll(".tab[role=tab]")];
    const i = tabs.indexOf(tab);
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      this.select(tab.dataset.id);
    } else if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      const next = tabs[(i + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length];
      this.select(next.dataset.id);
      const again = this.root.querySelector(`.tab[data-id="${next.dataset.id}"]`);
      if (again) again.focus();
    }
  }

  onClick(event) {
    const target = event.target.closest("[data-action]");
    if (!target || !this.root.contains(target)) return;
    // tarefas, post-its e tags tratam os próprios botões; sem isto "Novo post-it" também abria um terminal
    if (target.closest(".tasks, .notes, .session-tags")) return;
    const { action, id } = target.dataset;
    if (action === "select") this.select(id);
    if (action === "close") {
      event.stopPropagation();
      this.closeTerminal(id);
    }
    if (action === "new") this.newTerminal();
    if (action === "find") this.openSearch();
    if (action === "copy-output") this.copyOutput();
    if (action === "leave-history") {
      this.activeId = this.lastLiveId();
      this.requestedId = null;
      this.render();
      if (this.options.onSelect) this.options.onSelect(this.activeId);
    }
    if (action === "quick") {
      this.closeCommands();
      this.newTerminal(target.dataset.command, target.dataset.label);
    }
    if (action === "commands") this.toggleCommands();
    if (action === "add-cmd") this.addCommand();
    if (action === "copy-cmd") {
      event.stopPropagation();
      copy(target.dataset.command, "Comando copiado.");
    }
    if (action === "del-cmd") {
      event.stopPropagation();
      this.removeCommand(target.dataset.command);
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

  onDblClick(event) {
    const tab = event.target.closest(".tab[data-action='select']");
    if (!tab) return;
    const id = tab.dataset.id;
    const live = terminals.get(id);
    const record = this.records.get(id);
    const label = tab.querySelector(".tab-label");
    if (!label || (!live && !record)) return;
    const input = document.createElement("input");
    input.className = "tab-rename";
    input.value = live ? live.info.title : record.title;
    label.replaceWith(input);
    input.focus();
    input.select();
    let done = false;
    const finish = async (save) => {
      if (done) return;
      done = true;
      const title = input.value.trim();
      if (save && title) {
        try {
          if (live) await terminals.rename(id, title);
          else await patch(`/api/sessions/${id}`, { title });
          await this.loadSessions();
        } catch (err) {
          reportError(err);
        }
      }
      this.renderTabs();
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") finish(true);
      if (e.key === "Escape") finish(false);
    });
    input.addEventListener("blur", () => finish(true));
  }

  // ── desenho ────────────────────────────────────────────────────────────
  render() {
    const ids = this.tabIds();
    // antes da primeira carga a sessão pedida pela rota pode ainda não ter registro
    const waiting = !this.loaded && this.activeId && this.activeId === this.requestedId;
    if (!waiting && !ids.includes(this.activeId) && !this.isHistory()) this.activeId = this.lastLiveId();
    if (this.splitId && (!this.isLive(this.splitId) || this.mode !== "terminal")) this.splitId = null;
    this.renderTabs();
    this.renderContent();
  }

  renderTabs() {
    const ids = this.tabIds();
    const tabs = ids.map((id, i) => {
      const live = terminals.get(id);
      const record = this.records.get(id);
      const title = live ? live.info.title : record ? record.title : id;
      const active = id === this.activeId;
      const shown = id === this.splitId;
      const popped = terminals.popped.has(id);
      const site = live ? live.info.site : record && record.site;
      const where = this.options.scope === "all" && site ? `<span class="tab-site">${esc(site)}</span>` : "";
      const theme = (live && live.info.theme) || (record && record.theme) || null;
      const cls = [active && "is-active", shown && "is-shown", popped && "is-popped", !live && "is-closed",
        live && !live.alive && "is-dead", live && live.disconnected && "is-disconnected",
        theme && `has-theme t-${theme}`].filter(Boolean).join(" ");
      const tip = live ? shortPath(live.info.cwd) : `Encerrada ${formatStamp(record && record.closed_at)}`;
      const state = live && live.disconnected ? " · desconectado: Enter no terminal reconecta" : "";
      return `<div class="tab ${cls}" role="tab" tabindex="${active ? 0 : -1}" aria-selected="${active}" data-action="select" data-id="${id}" title="${esc(tip + state)}">
          ${icon(!live ? "clock" : popped ? "external" : "terminal")}
          <span class="tab-label">${esc(title)}</span>${where}
          ${live && live.alive && live.info.long_running ? `<span class="tab-long" title="Processo longo: ${esc(live.info.command)}">longo</span>` : ""}
          ${live && i < 9 && !isNative ? `<kbd class="tab-kbd">${isMac ? "⌘" : "Ctrl+⇧+"}${i + 1}</kbd>` : ""}
          <button class="tab-close" data-action="close" data-id="${id}" aria-label="${live ? "Fechar terminal" : "Tirar da barra"}"
            title="${live ? "Fechar terminal e salvar a memória" : "Tirar da barra (a memória continua salva)"}">${icon("x")}</button>
        </div>`;
    }).join("");

    // o histórico de sessões encerradas fica na barra lateral (pasta Histórico)


    const terminalTools = this.mode === "terminal" && this.isLive(this.activeId) ? `
      <button class="icon-btn ${this.splitId ? "is-on" : ""}" data-action="split" title="Dividir" aria-label="Dividir">${icon("split")}</button>
      <button class="icon-btn" data-action="find" title="Buscar no terminal (${isMac ? "⌘F" : "Ctrl+⇧+F"})" aria-label="Buscar no terminal">${icon("search")}</button>
      <button class="icon-btn" data-action="copy-output" title="Copiar a saída do terminal" aria-label="Copiar a saída do terminal">${icon("copy")}</button>
      <button class="icon-btn" data-action="popout" title="Destacar em janela (⇧⌘D)" aria-label="Destacar em janela">${icon("external")}</button>
      <button class="icon-btn" data-action="document" data-id="${this.activeId}" title="Documentar esta sessão com IA" aria-label="Documentar com IA">${icon("book")}</button>` : "";

    const viewing = this.isHistory() ? this.records.get(this.activeId) : null;
    const historyChip = viewing ? `
      <div class="history-chip" title="Sessão encerrada, aberta pela pasta Histórico">
        ${icon("clock")}<span>Histórico · ${esc(viewing.title)}</span>
        <button class="tab-close" data-action="leave-history" aria-label="Voltar aos terminais" title="Voltar aos terminais">${icon("x")}</button>
      </div>` : "";
    this.strip.innerHTML = `
      <div class="tabs">${tabs}</div>${historyChip}
      <button class="icon-btn" data-action="new" title="Novo terminal (${isMac ? "⌘T" : "Ctrl+⇧+T"})" aria-label="Novo terminal">${icon("plus")}</button>
      <div class="tabstrip-spacer"></div>
      ${this.options.scope === "site" && this.commands ? `<button class="btn btn-sm cmd-btn" data-action="commands" aria-haspopup="menu" title="Comandos do projeto">${icon("play")}<span>Comandos</span></button>` : ""}
      ${this.runtimeChip()}
      ${terminalTools}`;
    $$(".tab.is-active", this.strip).forEach((t) => t.scrollIntoView({ block: "nearest", inline: "nearest" }));
    const activeLive = this.mode === "terminal" ? terminals.get(this.activeId) : null;
    this.promptBar.update(activeLive ? activeLive.info.cwd : null, activeLive ? activeLive.info.id : null);
    if (this.options.onChange) this.options.onChange(this.sessions().length);
  }

  // ── comandos do projeto (vt-04 C2) ─────────────────────────────────────
  sitePath() {
    return `/api/sites/${encodeURIComponent(this.options.site.name)}/commands`;
  }

  async loadCommands() {
    if (this.options.scope !== "site" || !this.options.site) return;
    try {
      this.commands = (await get(this.sitePath())).commands;
      this.renderTabs();
      if (this.mode === "terminal" && !this.sessions().length) this.renderContent();
    } catch {
      /* site manual sem pasta ou servidor fora: fica sem o botão */
    }
  }

  async toggleCommands() {
    if (this.commandMenu && this.commandMenu.isConnected) return this.closeCommands();
    // vt-04 C4: os últimos comandos digitados nas sessões do site vêm logo abaixo
    const recent = await get(`/api/sites/${encodeURIComponent(this.options.site.name)}/recent`)
      .then((d) => d.commands).catch(() => []);
    this.closeCommands();  // a barra foi redesenhada com o menu aberto: limpa o ouvinte antigo
    const anchor = $(".cmd-btn", this.strip);
    if (!anchor || !this.commands) return null;
    const menu = document.createElement("div");
    menu.className = "cmd-menu";
    menu.setAttribute("role", "menu");
    menu.innerHTML = this.commands.map((c) => `<div class="cmd-row">
        <button class="cmd-item" role="menuitem" data-action="quick" data-command="${esc(c.command)}" data-label="${esc(c.label)}">
          ${icon("play")}<span class="cmd-label">${esc(c.label)}</span><code>${esc(c.command)}</code></button>
        ${c.custom ? `<button class="icon-btn icon-btn-sm" data-action="del-cmd" data-command="${esc(c.command)}" aria-label="Tirar ${esc(c.label)}" title="Tirar da lista">${icon("x")}</button>` : ""}
      </div>`).join("") + `<button class="cmd-item cmd-add" role="menuitem" data-action="add-cmd">${icon("plus")}<span>Adicionar comando…</span></button>`
      + (recent.length ? `<div class="cmd-group">${icon("history")}Últimos comandos</div>` + recent.map((c) => `<div class="cmd-row">
        <button class="cmd-item" role="menuitem" data-action="quick" data-command="${esc(c.command)}" data-label="${esc(c.command.slice(0, 40))}"
          title="Rodar de novo numa aba nova"><code class="cmd-recent">${esc(c.command)}</code></button>
        <button class="icon-btn icon-btn-sm" data-action="copy-cmd" data-command="${esc(c.command)}" aria-label="Copiar" title="Copiar">${icon("copy")}</button>
      </div>`).join("") : "");
    this.strip.appendChild(menu);
    const box = anchor.getBoundingClientRect();
    const host = this.strip.getBoundingClientRect();
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
      title: "Adicionar comando ao projeto",
      body: `<label class="field-label" for="cmd-command">Comando</label>
        <input id="cmd-command" class="input" data-command spellcheck="false" placeholder="php artisan queue:work">
        <label class="field-label" for="cmd-label">Nome no menu (opcional)</label>
        <input id="cmd-label" class="input" data-label maxlength="60">`,
      confirmLabel: "Adicionar",
      onDecide: (answer, root) => {
        command = root.querySelector("[data-command]").value.trim();
        label = root.querySelector("[data-label]").value.trim();
      },
    });
    if (!yes || !command) return;
    try {
      this.commands = (await post(this.sitePath(), { label: label || command, command })).commands;
      this.renderTabs();
    } catch (err) {
      reportError(err);
    }
  }

  async removeCommand(command) {
    this.closeCommands();
    try {
      this.commands = (await del(`${this.sitePath()}?command=${encodeURIComponent(command)}`)).commands;
      this.renderTabs();
    } catch (err) {
      reportError(err);
    }
  }

  /** vt-04 C1: PHP e Node que o backend usa para o site, com aviso se a aba não passa pelos shims do Lerd. */
  async loadRuntime() {
    if (this.options.scope !== "site" || !this.options.site) return;
    try {
      this.runtime = await get(`/api/sites/${encodeURIComponent(this.options.site.name)}/runtime`);
      this.renderTabs();
    } catch {
      /* sem backend ou fora do ar: a barra fica sem o chip */
    }
  }

  runtimeChip() {
    const r = this.runtime;
    if (!r || !(r.php || r.node)) return "";
    const warn = r.shim && !r.shim.ok ? r.shim.warning : "";
    const text = [r.php && `PHP ${r.php}`, r.node && `Node ${r.node}`].filter(Boolean).join(" · ");
    const tip = warn || `Versões que o backend usa neste site${r.docroot ? `; raiz ${r.docroot}` : ""}`;
    return `<span class="runtime-chip ${warn ? "is-warn" : ""}" title="${esc(tip)}">${warn ? icon("alert") : ""}${esc(text)}</span>`;
  }

  destroyChild() {
    if (this.child && this.child.destroy) this.child.destroy();
    this.child = null;
    this.childKey = "";
  }

  renderContent() {
    const id = this.activeId;
    const live = this.isLive(id);
    const record = this.records.get(id);
    if (this.mode === "terminal") {
      this.destroyChild();
      this.resizeObserver.disconnect();
      if (live) return this.renderPanes();
      if (id && record) return this.renderMemory(record);
      if (id && !record) {
        this.body.innerHTML = `<div class="loading"><span class="skeleton w-40"></span><span class="skeleton w-70"></span></div>`;
        return null;
      }
      this.body.innerHTML = this.emptyHtml();
      return null;
    }
    const key = `${this.mode}:${id || "-"}:${this.focus || ""}`;
    if (key === this.childKey && this.child) return null;
    this.destroyChild();
    this.resizeObserver.disconnect();
    // contêiner novo por aba: ouvintes da aba anterior não podem duplicar ações (post-it criado duas vezes)
    this.body.innerHTML = "";
    const host = document.createElement("div");
    host.className = "ws-child";
    this.body.appendChild(host);
    const onChange = () => {
      this.loadSoon();
      if (this.options.onDataChange) this.options.onDataChange();
    };
    const title = live ? terminals.get(id).info.title : record ? record.title : "";
    const common = { site: this.activeSite() || null, terminal: id, sessionTitle: title, sites: this.options.sites || [], onChange, focus: this.focus };
    if (this.mode === "tasks") this.child = new TasksView(host, common);
    if (this.mode === "debug" && this.options.site) this.child = new DebugView(host, { site: this.options.site });  // vt-06 C2
    if (this.mode === "harness" && this.options.site) this.child = new HarnessView(host, { site: this.options.site });  // vt-23 C2
    if (this.mode === "logs" && this.options.site) {  // vt-05 C6: só no site
      this.child = new LogsView(host, { site: this.options.site, onTerminal: async (tabId) => {
        await terminals.sync();
        // o roteador troca a seção do site e seleciona a aba sem remontar a tela
        location.hash = `#/sites/${encodeURIComponent(this.options.site.name)}/terminal/${tabId}`;
      } });
    }
    if (this.mode === "notes") this.child = new NotesView(host, common);
    if (this.mode === "tags") {
      if (id) this.child = new SessionTagsView(host, { ...common, sessionId: id });
      else this.body.innerHTML = this.emptyHtml("As tags pertencem a uma sessão de terminal. Abra um terminal para começar.");
    }
    this.childKey = key;
    return null;
  }

  renderPanes() {
    this.body.innerHTML = `<div class="panes ${this.splitId ? "is-split" : ""}"></div>`;
    const panes = $(".panes", this.body);
    const order = this.tabIds();
    const shownIds = [this.activeId, this.splitId].filter(Boolean).sort((a, b) => order.indexOf(a) - order.indexOf(b));
    for (const id of shownIds) {
      const session = terminals.get(id);
      const pane = document.createElement("div");
      pane.className = `pane ${this.splitId && id === this.activeId ? "is-focused" : ""}${session && session.info.theme ? ` has-theme t-${session.info.theme}` : ""}`;
      pane.dataset.session = id;
      pane.addEventListener("mousedown", () => this.focusPane(id), true);
      panes.appendChild(pane);
      if (!session) continue;
      if (terminals.popped.has(id)) {
        pane.innerHTML = `
          <div class="term-empty is-compact"><div class="term-empty-inner">
            ${icon("external", "i-lg")}
            <h3>${esc(session.info.title)} está numa janela própria</h3>
            <p>A sessão continua a mesma; feche a janela para trazê-la de volta.</p>
            <button class="btn" data-action="focus-popout" data-id="${id}">Mostrar janela</button>
          </div></div>`;
      } else {
        session.mount(pane);
        this.resizeObserver.observe(pane);
      }
    }
  }

  async renderMemory(record) {
    const id = record.id;
    const view = record.has_doc ? this.memoryView : "memory";
    this.body.innerHTML = `
      <div class="memory">
        <div class="memory-bar">
          ${icon("clock")}
          <span class="memory-title">${esc(record.title)}</span>
          <span class="dim">encerrada ${esc(formatStamp(record.closed_at))} · ${record.commands} ${record.commands === 1 ? "comando" : "comandos"}</span>
          ${record.has_doc ? `<div class="segmented" role="tablist" aria-label="Conteúdo">
            <button class="seg ${view === "memory" ? "is-on" : ""}" data-action="memory-view" data-view="memory" role="tab" aria-selected="${view === "memory"}">Memória</button>
            <button class="seg ${view === "doc" ? "is-on" : ""}" data-action="memory-view" data-view="doc" role="tab" aria-selected="${view === "doc"}">${icon("book")}<span>Documentação</span></button>
          </div>` : ""}
          <div class="spacer"></div>
          ${record.memory_file ? `<button class="btn btn-ghost btn-sm" data-action="open-memory" data-id="${id}" data-file="${view}">${icon("external")}<span>Abrir arquivo</span></button>` : ""}
          <button class="btn btn-ghost btn-sm" data-action="document" data-id="${id}">${icon("book")}<span>${record.has_doc ? "Refazer documentação" : "Documentar com IA"}</span></button>
          <button class="btn btn-sm" data-action="new">${icon("plus")}<span>Novo terminal</span></button>
        </div>
        <article class="memory-doc md"><div class="loading"><span class="skeleton w-40"></span><span class="skeleton w-70"></span></div></article>
      </div>`;
    try {
      const data = view === "doc" ? await get(`/api/sessions/${id}/doc`) : await get(`/api/sessions/${id}`);
      if (this.activeId !== id || this.mode !== "terminal") return;
      const doc = $(".memory-doc", this.body);
      const text = view === "doc" ? data.markdown : data.memory;
      if (doc) doc.innerHTML = text ? renderMarkdown(text) : `<p class="dim">A memória desta sessão ainda não foi gravada.</p>`;
    } catch (err) {
      reportError(err);
    }
  }

  emptyHtml(message) {
    const site = this.options.site;
    // vt-04 C2: no site, os comandos do projeto (os 6 primeiros); fora dele, os genéricos
    const list = this.options.scope === "site" && this.commands ? this.commands.slice(0, 6)
      : QUICK.filter((q) => !q.when || q.when(site));
    const quick = list
      .map((q) => `<button class="chip-btn" data-action="quick" data-command="${esc(q.command)}" data-label="${esc(q.label)}">
          ${icon("play")}<span>${esc(q.label)}</span></button>`)
      .join("");
    const where = site ? shortPath(site.path) : "~";
    return `
      <div class="term-empty">
        <div class="term-empty-inner">
          <div class="term-empty-prompt"><span class="prompt-path">${esc(where)}</span> <span class="prompt-caret"></span></div>
          <h3>${site ? `Nenhum terminal aberto em ${esc(site.name)}` : "Nenhum terminal aberto"}</h3>
          <p>${esc(message || "Cada terminal é uma sessão: as tarefas, post-its e tags que você criar nela viram a memória em Markdown quando ele for fechado.")}</p>
          <div class="term-empty-actions">
            <button class="btn btn-primary" data-action="new">${icon("plus")}<span>Novo terminal</span><kbd>${isMac ? "⌘T" : "Ctrl+⇧+T"}</kbd></button>
            ${quick}
          </div>
        </div>
      </div>`;
  }

  // ── busca (vt-19 C3) ────────────────────────────────────────────────────
  bindSearch() {
    const input = $(".term-search-input", this.searchBar);
    input.addEventListener("input", () => this.find("type"));
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        this.find(e.shiftKey ? "prev" : "next");
      }
      if (e.key === "Escape") {
        e.preventDefault();
        this.closeSearch();
      }
    });
    this.searchBar.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-search]");
      if (!btn) return;
      if (btn.dataset.search === "close") this.closeSearch();
      else this.find(btn.dataset.search);
    });
  }

  searchTarget() {
    const session = terminals.get(this.activeId);
    return session && session.search ? session : null;
  }

  openSearch() {
    if (this.mode !== "terminal" || !this.searchTarget()) return false;
    this.searchBar.hidden = false;
    const input = $(".term-search-input", this.searchBar);
    input.focus();
    input.select();
    if (input.value) this.find("type");
    return true;
  }

  closeSearch() {
    this.searchBar.hidden = true;
    const session = this.searchTarget();
    if (session) {
      session.search.clearDecorations();
      session.focus();
    }
  }

  find(direction) {
    const session = this.searchTarget();
    const query = $(".term-search-input", this.searchBar).value;
    const count = $(".term-search-count", this.searchBar);
    if (!session) return;
    if (this.searchSub !== session) {
      if (this.searchListener) this.searchListener.dispose();
      this.searchListener = session.search.onDidChangeResults(({ resultIndex, resultCount }) => {
        count.textContent = resultCount ? `${resultIndex >= 0 ? resultIndex + 1 : "?"} de ${resultCount}` : "0 de 0";
      });
      this.searchSub = session;
    }
    if (!query) {
      session.search.clearDecorations();
      count.textContent = "";
      return;
    }
    const options = { incremental: direction === "type", decorations: SEARCH_DECORATIONS };
    if (direction === "prev") session.search.findPrevious(query, options);
    else session.search.findNext(query, options);
  }

  /** Copia a saída do terminal: o serialize junta as linhas que o terminal quebrou só na tela (D-011). */
  copyOutput() {
    const session = terminals.get(this.activeId);
    if (!session) return;
    const raw = session.serializer ? session.serializer.serialize({ excludeModes: true, excludeAltBuffer: true }) : "";
    const text = raw.replace(ANSI, "").replace(/\r\n/g, "\n").replace(/[ \t]+$/gm, "").trimEnd();
    copy(text, "Saída do terminal copiada.");
  }

  destroy() {
    this.closeCommands();  // tira o ouvinte do menu de comandos do documento
    if (this.searchListener) this.searchListener.dispose();
    this.unsubscribe();
    this.offJobs();
    this.promptBar.destroy();
    window.removeEventListener("vulcan-sessions-changed", this.onSessionsChanged);
    this.resizeObserver.disconnect();
    this.destroyChild();
    // as sessões ficam no pool: sair da tela não encerra terminais
    this.sessions().forEach((s) => s.el.remove());
  }
}

export function mountPopout(root, id) {
  root.innerHTML = `<div class="popout"><div class="popout-bar" data-drag><span class="popout-title"></span></div><div class="pane popout-pane"></div></div>`;
  terminals.sync().then(() => {
    const session = terminals.get(id);
    const title = $(".popout-title", root);
    if (!session) {
      $(".popout-pane", root).innerHTML = `<div class="term-empty"><div class="term-empty-inner"><h3>Terminal encerrado</h3>
        <p>Esta sessão não existe mais.</p><button class="btn" data-close>Fechar janela</button></div></div>`;
      root.querySelector("[data-close]").addEventListener("click", () => native({ type: "close" }) || window.close());
      return;
    }
    title.textContent = `${session.info.title} · ${shortPath(session.info.cwd)}`;
    session.mount($(".popout-pane", root));
    new ResizeObserver(() => session.resizeSoon()).observe($(".popout-pane", root));
    session.focus();
  }).catch(reportError);
}
