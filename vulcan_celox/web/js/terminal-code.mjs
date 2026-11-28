// Code workspace attached to a terminal. A context owns its tree, viewer and poll.
import { CodexComposer } from "./codex-composer.mjs";
import { openDraftShelf } from "./codex-shelf.mjs";
import { get, post } from "./api.mjs";
import { esc, icon } from "./dom.mjs";
import { t } from "./i18n.mjs";
import { terminals } from "./terminal-pool.mjs";
import { Marks } from "./views/code/code-live.mjs";
import { ExplorerFollow } from "./views/code/explorer-follow.mjs";
import { LivePoll } from "./views/code/explorer-live.mjs";
import { addFolderForm, pickFolder } from "./views/code/explorer-roots.mjs";
import { FileTree, loadWunderbaum } from "./views/code/explorer-tree.mjs";
import { ExplorerViewer, query } from "./views/code/explorer-viewer.mjs";

const COLUMN = "vulcan-session-files";
const LIMIT = 200;

export class TerminalCode {
  constructor(workspace, host) {
    this.ws = workspace;
    this.host = host;
    this.mode = "terminal";
    this.ticket = 0;
    this.root = null;
    this.expanded = false;
    try { this.expanded = localStorage.getItem(COLUMN) === "true"; } catch { /* window only */ }
    this.marks = new Marks();
    host.insertAdjacentHTML("beforeend", `<section class="session-code" aria-label="${t("Código da sessão")}" hidden>
      <header class="session-code-tools">
        <button type="button" class="btn btn-sm" data-sc="codex" aria-expanded="false">Codex</button>
        <button type="button" class="btn btn-sm" data-sc="files" aria-expanded="false">${icon("tree")}${t("Arquivos")}</button>
        <button type="button" class="btn btn-sm" data-sc="folder" aria-expanded="false">${icon("folder-plus")}${t("Abrir pasta")}</button>
        <button type="button" class="btn btn-sm ce-follow" data-sc="follow" hidden></button>
        <button type="button" class="icon-btn" data-sc="expand" aria-pressed="false" aria-label="${t("Ampliar visor")}" title="${t("Ampliar visor")}">${icon("external")}</button>
      </header>
      <div class="session-code-folder" hidden>${addFolderForm()}</div>
      <p class="session-code-root mono"></p><p class="session-code-status" role="status"></p>
      <div class="codex-composer" hidden></div>
      <div class="ce-view session-code-view"></div>
    </section>
    <aside class="session-files" aria-label="${t("Arquivos")}" hidden>
      <header class="session-files-top">
        <div class="segmented" role="group" aria-label="${t("Arquivos")}">
          <button type="button" class="seg is-on" data-sc="tree" aria-pressed="true">${t("Árvore")}</button>
          <button type="button" class="seg" data-sc="changes" aria-pressed="false">${t("Alterações")}</button>
        </div>
        <button type="button" class="icon-btn" data-sc="close" aria-label="${t("Fechar arquivos")}">${icon("x")}</button>
      </header>
      <div class="ce-tree session-code-tree"><div></div></div>
      <section class="session-changes" aria-label="${t("Alterações")}" hidden>
        <p class="session-period"></p><ol class="session-events"></ol>
      </section>
    </aside>`);
    this.center = host.querySelector(".session-code");
    this.column = host.querySelector(".session-files");
    this.treeEl = host.querySelector(".session-code-tree");
    this.error = host.querySelector(".session-code-status");
    this.form = host.querySelector("[data-ce-add]");
    this.viewer = new ExplorerViewer(host.querySelector(".session-code-view"));
    this.follow = new ExplorerFollow(this.button("follow"), (path) => this.followTo(path));
    this.layout = new ResizeObserver(() => this.paintVisibility());
    this.layout.observe(host);
    this.viewGesture = () => { this.manual += 1; this.follow.gesture(); };
    for (const target of [this.viewer.body.parentElement, this.column]) {
      for (const event of ["pointerdown", "keydown", "wheel"]) target.addEventListener(event, this.viewGesture, { passive: true });
    }
    this.click = (event) => this.clicked(event);
    this.key = (event) => {
      if (event.key === "Escape" && !this.column.hidden && this.column.classList.contains("is-drawer") &&
          !document.querySelector("dialog[open]")) {
        event.preventDefault();
        this.setColumn(false, true);
      }
    };
    host.addEventListener("click", this.click);
    document.addEventListener("keydown", this.key);
    this.form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (this.form.elements.path.value.trim()) this.addRoot(this.form.elements.path.value.trim());
    });
  }

  button(action) { return this.host.querySelector(`[data-sc="${action}"]`); }

  inContext(ticket, root = this.root) {
    return !this.destroyed && this.host.isConnected && this.ticket === ticket && this.root === root &&
      [this.id, this.handoffId].includes(this.ws.activeId) && this.ws.mode === "terminal";
  }

  sync(terminal) {
    const id = terminal?.info.id || null;
    if (this.id === id || (id && this.handoffId === id)) return;
    this.reset();
    this.id = id;
    this.composer?.sync();
    if (id) this.resolveRoot();
    else this.showTerminal();
  }

  reset() {
    this.ticket += 1;
    this.manual = 0;
    this.root = null;
    this.started = null;
    this.lost = false;
    this.last = new Map();
    this.events = [];
    this.poll?.stop();
    this.poll = null;
    if (this.tree) {
      this.tree.destroy();
      this.treeEl.replaceChildren(document.createElement("div"));
      this.tree = null;
    }
    this.follow.reset();
    this.marks.clear();
    this.viewer.reset(null);
    this.error.textContent = "";
    this.host.querySelector(".session-code-root").textContent = "";
    this.button("follow").hidden = true;
    this.showFolder(false);
    this.paintChanges();
  }

  showTerminal({ focus = false } = {}) {
    this.mode = "terminal";
    this.paintVisibility();
    if (focus) this.ws.visible().find((session) => session.info.id === this.ws.activeId)?.focus();
  }

  focusDestination(id) {
    this.showTerminal();
    this.handoffId = id === this.id ? null : id;
    this.ws.select(id, { handoff: true });
    this.ws.renderTabs();
  }

  toggleComposer() {
    const host = this.host.querySelector(".codex-composer");
    this.composer ||= new CodexComposer(this, host);
    this.composer.sync();
    host.hidden = !host.hidden;
    this.button("codex").setAttribute("aria-expanded", String(!host.hidden));
    if (!host.hidden) this.composer.area.focus();
  }

  search() {
    this.viewer.search();
    return true;
  }

  showCode() {
    this.mode = "code";
    this.sync(this.ws.isHistory() ? null : terminals.get(this.ws.activeId));
    this.paintVisibility();
  }

  paintVisibility() {
    const reading = this.mode === "code";
    const beside = window.innerWidth >= 1080 && this.host.clientWidth >= 500 + 288;
    const large = this.center.classList.contains("is-expanded");
    this.center.hidden = !reading;
    this.ws.body.hidden = reading;
    this.column.classList.toggle("is-drawer", !beside);
    this.column.hidden = !this.expanded || large || !this.id || (!reading && !beside);
    this.button("files").setAttribute("aria-expanded", String(!this.column.hidden));
  }

  setColumn(open, focus = false) {
    this.expanded = open;
    if (open) this.setExpanded(false);
    try { localStorage.setItem(COLUMN, String(open)); } catch { /* window only */ }
    this.paintVisibility();
    if (focus) (open ? this.button("close") : this.button("files")).focus();
  }

  setExpanded(expanded) {
    this.center.classList.toggle("is-expanded", expanded);
    this.button("expand").setAttribute("aria-pressed", String(expanded));
    this.paintVisibility();
  }

  showFolder(open) {
    this.form.parentElement.hidden = !open;
    this.button("folder").setAttribute("aria-expanded", String(open));
    this.form.querySelector("[data-ce-error]").hidden = true;
    if (open) this.form.elements.path.focus();
  }

  async resolveRoot() {
    const ticket = this.ticket;
    this.viewer.message(t("Carregando…"), "");
    try {
      const data = await get(`/api/files/roots?${query({ terminal: this.id })}`);
      if (!this.inContext(ticket)) return;
      if (data.context.root) return this.openRoot(data.context.root);
      this.viewer.message(t("Nenhuma pasta para abrir"), t("Use Abrir pasta para escolher a raiz desta aba."));
    } catch (err) {
      if (this.inContext(ticket)) this.error.textContent = err.message;
    }
    return undefined;
  }

  async addRoot(path) {
    const ticket = this.ticket;
    const error = this.form.querySelector("[data-ce-error]");
    error.hidden = true;
    try {
      const { added } = await post("/api/files/roots", { path });
      if (this.inContext(ticket)) await this.openRoot(added);
    } catch (err) {
      if (!this.inContext(ticket)) return;
      error.textContent = err.message;
      error.hidden = false;
    }
  }

  async openRoot(root) {
    this.reset();
    this.root = root;
    this.host.querySelector(".session-code-root").textContent = root;
    this.composer?.sync();
    const ticket = this.ticket;
    this.viewer.reset(root);
    this.viewer.message(t("Carregando…"), "");
    const load = (path) => get(`/api/files/tree?${query({ root, path })}`);
    try {
      const [listing, WB] = await Promise.all([load(""), loadWunderbaum()]);
      if (!this.inContext(ticket, root)) return;
      const tree = new FileTree(WB, this.treeEl.firstElementChild, {
        marks: this.marks, label: t("Árvore de arquivos"), load,
        onOpen: (path) => {
          if (!this.inContext(ticket, root)) return;
          this.showCode();
          this.openFile(path, false);
        },
        onExpand: () => {},
      });
      this.tree = tree;
      await tree.show(listing);
      if (!this.inContext(ticket, root)) return;
      this.viewer.message(t("Escolha um arquivo"), t("Clique num arquivo da árvore, ou use as setas e Enter."));
      this.button("follow").hidden = false;
      this.poll = new LivePoll(root, () => ({ file: this.viewer.path, open: [...tree.expanded] }),
        (data) => this.inContext(ticket, root) && this.changes(data), {
          source: "disk",
          onError: () => { if (this.inContext(ticket, root)) this.error.textContent = t("Acompanhamento indisponível. Tentando reconectar."); },
        });
    } catch (err) {
      if (this.inContext(ticket, root)) this.error.textContent = err.message;
    }
  }

  async changes(data) {
    const context = this.ticket;
    if (data.missing) {
      this.lost = true;
      this.error.textContent = t("A pasta não existe mais");
      return;
    }
    const reset = data.reset || this.lost;
    if (reset) {
      const ticket = this.ticket;
      const root = this.root;
      const listing = await get(`/api/files/tree?${query({ root })}`);
      if (!this.inContext(ticket, root)) return;
      this.follow.reset();
      this.last.clear();
      this.marks.clear();
      await this.tree.show(listing);
      if (!this.inContext(ticket, root)) return;
      await this.viewer.refresh();
      if (!this.inContext(ticket, root)) return;
      this.lost = false;
    }
    this.started ??= new Date();
    const notices = [];
    if (data.partial) notices.push(t("Pasta grande: só o que está aberto é observado"));
    if (data.interval > 3) notices.push(t("A atualização pode levar {n} s.", { n: Math.ceil(data.interval) }));
    if (reset) notices.push(t("A observação foi retomada com uma nova referência."));
    this.error.textContent = notices.join(" · ");
    for (const event of data.events) {
      this.marks.apply(event);
      this.tree.applyEvent(event);
      for (const key of this.last.keys()) {
        if (event.rel === key || (event.change === "deleted" && key.startsWith(event.rel + "/"))) this.last.delete(key);
      }
      if (event.kind === "file" && event.change !== "deleted" && !event.sensitive && !event.ignored) {
        this.last.set(event.rel, event);
        if (this.last.size > LIMIT) this.last.delete(this.last.keys().next().value);
      }
    }
    if (data.events.length) this.events = [...[...data.events].reverse(), ...this.events].slice(0, LIMIT);
    this.paintChanges();
    const path = this.viewer.path;
    if (path && (this.viewer.stale || data.events.some((e) => e.rel === path))) await this.viewer.refresh();
    if (this.inContext(context)) this.follow.events([...this.last.values()].slice(-1), data.cursor, this.viewer.path);
  }

  async followTo(path) {
    const ticket = this.ticket;
    const root = this.root;
    const manual = this.manual;
    if (!this.last.has(path)) return;
    for (const candidate of [...this.last.keys()].reverse()) {
      if (candidate === this.viewer.path) return;
      const canRead = await this.viewer.readable(candidate);
      if (!this.inContext(ticket, root) || manual !== this.manual || !this.follow.following) return;
      if (canRead && this.last.has(candidate)) return this.openFile(candidate);
    }
  }

  openFile(path, reveal = true) {
    if (reveal) this.tree?.reveal(path).catch(() => {});
    return this.viewer.open(path);
  }

  paintChanges() {
    const period = this.host.querySelector(".session-period");
    period.textContent = this.started ? t("Desde {time}", { time: this.started.toLocaleTimeString() }) : "";
    const list = this.host.querySelector(".session-events");
    const open = document.activeElement?.dataset.scPath;
    const html = this.events.map(({ rel, kind, sensitive, change }) => {
      const label = { added: t("Criado"), modified: t("Modificado"), deleted: t("Removido") }[change];
      const title = `<span class="mono">${esc(rel)}</span><small>${label} · ${t("Mudança no disco")}</small>`;
      return `<li>${kind !== "dir" && !sensitive ? `<button type="button" data-sc-path="${esc(rel)}">${title}</button>` : title}</li>`;
    }).join("");
    if (list.markup === html) return;
    list.markup = html;
    list.innerHTML = html;
    if (open) list.querySelector(`[data-sc-path="${CSS.escape(open)}"]`)?.focus({ preventScroll: true });
  }

  clicked(event) {
    const action = event.target.closest("[data-sc], [data-sc-path], [data-ce=pick]");
    if (!action) return;
    if (action.dataset.scPath) {
      this.showCode();
      this.openFile(action.dataset.scPath);
      return;
    }
    const name = action.dataset.sc;
    if (name === "codex") this.toggleComposer();
    if (name === "files") this.setColumn(this.column.hidden, true);
    if (name === "close") this.setColumn(false, true);
    if (name === "expand") this.setExpanded(!this.center.classList.contains("is-expanded"));
    if (name === "folder") this.showFolder(this.form.parentElement.hidden);
    if (name === "follow") this.follow.toggle();
    if (name === "tree" || name === "changes") {
      this.treeEl.hidden = name !== "tree";
      this.host.querySelector(".session-changes").hidden = name !== "changes";
      for (const key of ["tree", "changes"]) {
        this.button(key).classList.toggle("is-on", key === name);
        this.button(key).setAttribute("aria-pressed", String(key === name));
      }
    }
    if (action.dataset.ce === "pick") {
      const ticket = this.ticket;
      const picker = this.form.elements.path.cloneNode();
      pickFolder(picker).then((path) => { if (path && this.inContext(ticket)) this.addRoot(path); });
    }
  }

  destroy() {
    this.destroyed = true;
    this.reset();
    this.ws.body.hidden = false;
    this.viewer.destroy();
    this.composer?.destroy();
    this.follow.destroy();
    this.layout.disconnect();
    document.removeEventListener("keydown", this.key);
    this.host.removeEventListener("click", this.click);
    this.center.remove();
    this.column.remove();
  }
}

export function showSessionMode(ws, code, { focus = true } = {}) {
  if (!code) ws.code?.showTerminal();
  if (code && ws.options.sessionCode && terminals.get(ws.activeId)?.alive) {
    if (ws.code?.handoffId) {
      const source = ws.code.id;
      ws.code.handoffId = null;
      if (terminals.get(source)) ws.select(source, { handoff: true });
    }
    ws.code ||= new TerminalCode(ws, ws.body.parentElement);
    ws.code.showCode();
  }
  ws.renderTabs();
  if (!focus) return;
  if (code) ws.code?.button("files").focus();
  else if (!terminals.popped.has(ws.activeId)) terminals.get(ws.activeId)?.focus();
}

export function sessionTools(ws, action, target) {
  if (action === "session-code" || action === "session-pty") showSessionMode(ws, action === "session-code");
  if (action === "window-drafts") openDraftShelf(ws.code?.composer, target);
}
