// Code screen: the whole tree of a project and the viewer. Read-only: there is no write route under /api/files.

import { ApiError, del, get, isMac, post } from "../api.mjs";
import { icon, reportError } from "../dom.mjs";
import { t } from "../i18n.mjs";
import { Marks } from "./code/code-live.mjs";
import { ExplorerFollow } from "./code/explorer-follow.mjs";
import { LivePoll } from "./code/explorer-live.mjs";
import { FileTree, loadWunderbaum } from "./code/explorer-tree.mjs";
import { codeHash } from "./code/explorer-open.mjs";
import { bindResize, MIN_WIDTH } from "./code/explorer-layout.mjs";
import { openQuickOpen } from "./code/explorer-quick.mjs";
import { ExplorerSearch } from "./code/explorer-search.mjs";
import { ExplorerTabs } from "./code/explorer-tabs.mjs";
import { addFolderForm, missingHtml, noRootsHtml, pickFolder, refusedHtml, rootOptions, setWindowTitle, statusHtml } from "./code/explorer-roots.mjs";
import { ExplorerViewer, query } from "./code/explorer-viewer.mjs";

const QUICK_KEY = isMac ? "⌘P" : "Ctrl+⇧+P";
const LAST_ROOT = "vulcan-code-last-root";
const WIDTH = "vulcan-code-tree-width";

function stored(key) {
  try { return localStorage.getItem(key); } catch (_) { return null; }
}

function store(key, value) {
  try { localStorage.setItem(key, value); } catch (_) { /* no storage: applies only now */ }
}

export class CodeExplorerView {
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.roots = [];
    this.current = null;
    this.tree = null;
    this.marks = new Marks();
    this.ticket = 0;
    this.pending = options.route || {};
    this.root.innerHTML = `<section class="ce" aria-label="${t("Código")}">
      <header class="ce-top">
        <label class="ce-root"><span class="sr-only">${t("Pasta aberta")}</span><select class="select" data-ce-root></select></label>
        <button type="button" class="btn btn-ghost btn-sm" data-ce="add" title="${t("Abrir outra pasta")}">${icon("folder-plus")}<span>${t("Abrir pasta")}</span></button>
        <button type="button" class="btn btn-ghost btn-sm" data-ce="remove" hidden title="${t("Tira da lista. Nada é apagado.")}">${icon("x")}<span>${t("Tirar da lista")}</span></button>
        <span class="spacer"></span>
        <button type="button" class="btn btn-sm ce-follow" data-ce="follow"></button>
        <span class="ce-readonly dim">${icon("lock")}<span>${t("Só leitura")}</span></span>
      </header>
      <div class="ce-addbar" data-ce-addbar hidden>${addFolderForm()}</div>
      <div class="ce-notice" data-ce-notice hidden></div>
      <div class="ce-body" data-ce-body>
        <nav class="ce-side" aria-label="${t("Arquivos do projeto")}">
          <div class="ce-side-bar">
            <button type="button" class="btn btn-ghost btn-sm" data-ce="quick" title="${t("Ir para um arquivo pelo nome")}">${icon("file")}<span>${t("Ir para arquivo")}</span><kbd class="ce-kbd">${QUICK_KEY}</kbd></button>
            <button type="button" class="icon-btn" data-ce="search" aria-pressed="false" title="${t("Buscar texto nos arquivos do Git")}" aria-label="${t("Buscar texto nos arquivos do Git")}">${icon("search")}</button>
          </div>
          <div class="ce-searchpanel" data-ce-search hidden></div>
          <div class="ce-tree" data-ce-tree></div></nav>
        <div class="ce-handle" role="separator" aria-orientation="vertical" tabindex="0" aria-label="${t("Largura da árvore")}" data-ce-handle></div>
        <section class="ce-main code-main" aria-label="${t("Visor de código")}"><div class="ce-tabs" data-ce-tabs></div><div class="ce-view" data-ce-main></div></section>
      </div>
      <footer class="ce-status" data-ce-status></footer>
    </section>`;
    const $ = (s) => this.root.querySelector(s);
    this.bodyWrap = $("[data-ce-body]");
    this.side = $(".ce-side");
    this.treeEl = $("[data-ce-tree]");
    this.notice = $("[data-ce-notice]");
    this.status = $("[data-ce-status]");
    this.select = $("[data-ce-root]");
    this.addbar = $("[data-ce-addbar]");
    this.viewer = new ExplorerViewer($("[data-ce-main]"));
    this.tabs = new ExplorerTabs($("[data-ce-tabs]"), { open: (rel) => this.openFile(rel, { user: true }), empty: () => this.viewerIdle() });
    this.search = new ExplorerSearch($("[data-ce-search]"), $("[data-ce-tree]"), $("[data-ce=search]"), (rel, line) => this.openFile(rel, { line, user: true }));
    this.follow = new ExplorerFollow($("[data-ce=follow]"), (rel) => this.followTo(rel));
    // only user gestures pause; what the viewer does by itself does not pass through here
    const gesture = () => this.follow.gesture();
    this.bodyWrap.addEventListener("pointerdown", gesture);
    this.bodyWrap.addEventListener("wheel", gesture, { passive: true });
    this.bodyWrap.addEventListener("keydown", gesture);
    const width = Number(stored(WIDTH));
    if (width >= MIN_WIDTH) this.bodyWrap.style.setProperty("--ce-tree", `${width}px`);
    this.root.addEventListener("click", (e) => this.clicked(e));
    this.root.addEventListener("submit", (e) => this.submitted(e));
    this.select.addEventListener("change", () => this.options.navigate(codeHash(this.select.value)));
    bindResize($("[data-ce-handle]"), this.bodyWrap, this.side, (px) => store(WIDTH, String(px)));
    this.onKey = (e) => this.key(e);
    document.addEventListener("keydown", this.onKey, true);
    this.start();
  }

  // ── folders ─────────────────────────────────────────────────────────
  async start() {
    this.showLoading();
    try {
      this.roots = (await get("/api/files/roots")).roots;
    } catch (err) {
      reportError(err);
      return;
    }
    if (this.destroyed) return;
    const last = stored(LAST_ROOT);
    const wanted = this.pending.root || (this.roots.some((r) => r.path === last) ? last : this.roots[0] && this.roots[0].path);
    this.renderRoots();
    if (wanted) await this.openRoot(wanted, this.pending.file, this.pending.line);
    else this.showNotice(noRootsHtml());
  }

  renderRoots() {
    this.select.innerHTML = rootOptions(this.roots, this.current);
    this.select.hidden = !this.roots.length;
    const entry = this.roots.find((r) => r.path === this.current);
    this.root.querySelector("[data-ce=remove]").hidden = !(entry && entry.removable);
  }

  showLoading() {
    this.notice.hidden = true;
    this.bodyWrap.hidden = false;
    this.treeEl.innerHTML = `<div class="loading"><span class="skeleton w-70"></span><span class="skeleton w-55"></span><span class="skeleton w-40"></span></div>`;
    this.viewer.message(t("Carregando…"), "");
  }

  /** Replaces the tree and the viewer with one explanation and the next step. */
  showNotice(html) {
    this.stopRoot();
    this.bodyWrap.hidden = true;
    this.follow.button.hidden = true;  // nothing to follow without a tree
    this.status.innerHTML = "";
    this.notice.innerHTML = html;
    this.notice.hidden = false;
  }

  /** Opens a folder in the tree. A refused folder explains why and offers the way out. */
  async openRoot(root, file = null, line = 0) {
    this.stopRoot();
    const ticket = ++this.ticket;
    this.current = root;
    this.viewer.reset(root);
    this.marks.clear();
    this.showLoading();
    let listing;
    try {
      listing = await get(`/api/files/tree?${query({ root })}`);
    } catch (err) {
      if (ticket === this.ticket) this.rootFailed(root, err);
      return;
    }
    if (ticket !== this.ticket || this.destroyed) return;
    this.current = listing.root;
    this.viewer.reset(listing.root);
    store(LAST_ROOT, listing.root);
    if (!this.roots.some((r) => r.path === listing.root)) await this.reloadRoots();
    this.renderRoots();
    const entry = this.roots.find((r) => r.path === listing.root);
    setWindowTitle(entry ? entry.name : "");
    try {
      await this.mountTree(listing);
      this.follow.button.hidden = false;
      this.live = new LivePoll(listing.root, () => this.pollScope(), (data) => this.applyChanges(data));
    } catch (err) {
      this.viewer.message(t("Árvore indisponível"), t("A biblioteca da árvore não carregou. Reabra o app; se continuar, reinstale."));
      return;
    }
    if (ticket !== this.ticket) return;
    this.renderStatus();
    this.tabs.load(listing.root);
    this.search.setRoot(listing.root);
    this.hasEntries = listing.entries.length > 0;
    const again = file || this.tabs.active;
    if (again) await this.openFile(again, { line });
    else this.viewerIdle();
  }

  viewerIdle() {
    this.viewer.reset(this.current);
    this.viewer.message(this.hasEntries ? t("Escolha um arquivo") : t("Pasta vazia"),
      this.hasEntries ? t("Clique num arquivo da árvore, ou use as setas e Enter.") : t("Quando algo for escrito aqui, aparece na árvore."));
  }

  rootFailed(root, err) {
    const data = (err instanceof ApiError && err.data) || {};
    if (data.reason === "missing") this.showMissing(root);
    else this.showNotice(refusedHtml(root, err, data));
    this.renderRoots();
  }

  showMissing(root) {
    const entry = this.roots.find((r) => r.path === root);
    this.showNotice(missingHtml(root, entry && entry.removable));
  }

  async reloadRoots() {
    try {
      this.roots = (await get("/api/files/roots")).roots;
    } catch (_) { /* the list on screen stays */ }
  }

  async mountTree(listing) {
    const Wunderbaum = await loadWunderbaum();
    if (this.destroyed) return;
    if (this.tree) this.tree.destroy();
    // an element of its own for each folder: the library does not start twice on the same one
    this.treeEl.innerHTML = "<div></div>";
    const root = this.current;
    this.tree = new FileTree(Wunderbaum, this.treeEl.firstElementChild, {
      marks: this.marks, gitRoot: root,
      label: t("Árvore de arquivos"),
      load: (rel) => get(`/api/files/tree?${query({ root, path: rel })}`),
      onOpen: (rel) => this.openFile(rel, { user: true }),
      onExpand: () => {},
    });
    await this.tree.show(listing);
  }

  /** What the poll asks about: the open file and, when the server does not sweep them by itself, the open folders. */
  pollScope() {
    return { file: this.viewer.path || "", open: this.tree ? [...this.tree.expanded] : [] };
  }

  async applyChanges(data) {
    if (data.missing) {
      this.showMissing(this.current);
      return;
    }
    if (data.reset) {
      await this.reloadTree();
    }
    let openChanged = false;
    for (const event of data.events) {
      this.marks.apply(event);
      if (this.tree) this.tree.applyEvent(event);
      if (event.rel === this.viewer.path) openChanged = true;
      this.lastEvent = event;
    }
    this.follow.events(data.events, data.cursor, this.viewer.path);
    let attributed = false;
    for (const { rel, agent } of data.attributed || []) {
      if (this.marks.attribute(rel, agent)) {
        if (this.tree) this.tree.refresh(rel);
        attributed = true;
      }
      if (this.lastEvent && this.lastEvent.rel === rel) this.lastEvent.agent = agent;
    }
    if (attributed) this.renderStatus();
    this.partial = data.partial;
    this.watching = data.watching;
    if (data.events.length || this.partial !== this.shownPartial) this.renderStatus();
    if (openChanged || this.viewer.stale) await this.viewer.refresh({ reveal: this.follow.following });
  }

  async followTo(rel) {
    if (this.destroyed || !this.current || rel === this.viewer.path) return;
    if (!(await this.viewer.readable(rel)) || !this.follow.following) return;
    await this.openFile(rel);
    this.options.navigate(codeHash(this.current, rel), { silent: true });
  }

  /** The cursor got too old, or the watcher started over: the marks no longer mean anything. */
  async reloadTree() {
    try {
      const listing = await get(`/api/files/tree?${query({ root: this.current })}`);
      const open = this.tree ? [...this.tree.expanded] : [];
      this.marks.clear();
      await this.tree.show(listing);
      for (const key of open) {
        const node = this.tree.node(key);
        if (node) await node.setExpanded(true);
      }
    } catch (_) { /* the next round tries again */ }
  }

  stopRoot() {
    this.ticket += 1;
    if (this.live) this.live.stop();
    this.live = null;
    if (this.tree) this.tree.destroy();
    this.tree = null;
    this.lastEvent = null;
    if (this.follow) this.follow.reset();
  }

  async addFolder(path, errorEl) {
    try {
      const data = await post("/api/files/roots", { path });
      this.roots = data.roots;
      this.addbar.hidden = true;
      this.notice.hidden = true;
      this.options.navigate(codeHash(data.added));
    } catch (err) {
      if (!(err instanceof ApiError) || !errorEl) return reportError(err);
      errorEl.textContent = err.message;
      errorEl.hidden = false;
    }
    return undefined;
  }

  async removeRoot() {
    try {
      this.roots = (await del(`/api/files/roots?${query({ path: this.current })}`)).roots;
      this.current = null;
      store(LAST_ROOT, "");
      if (this.roots.length) {
        this.options.navigate(codeHash(this.roots[0].path), { replace: true });
      } else {
        this.options.navigate("#/codigo", { silent: true });
        this.renderRoots();
        this.showNotice(noRootsHtml());
      }
    } catch (err) {
      reportError(err);
    }
  }

  // ── viewer ──────────────────────────────────────────────────────────
  async openFile(rel, { line = 0, user = false } = {}) {
    this.tabs.add(rel);
    if (this.tree) this.tree.reveal(rel);
    if (user) this.options.navigate(codeHash(this.current, rel), { silent: true });
    const done = this.viewer.open(rel, { line });
    this.renderStatus();
    await done;
  }

  renderStatus() {
    const entry = this.roots.find((r) => r.path === this.current);
    this.status.innerHTML = statusHtml(entry ? entry.short : this.current || "", this.current || "", this.partial, this.lastEvent);
    this.shownPartial = this.partial;
  }

  // ── events ──────────────────────────────────────────────────────────
  clicked(event) {
    const action = event.target.closest("[data-ce]");
    if (!action) return undefined;
    const name = action.dataset.ce;
    if (name === "add") {
      this.addbar.hidden = !this.addbar.hidden;
      if (!this.addbar.hidden) this.addbar.querySelector("input").focus();
    }
    if (name === "remove") return this.removeRoot();
    if (name === "follow") return this.follow.toggle();
    if (name === "quick") return this.quickOpen();
    if (name === "search") return this.search.toggle();
    if (name === "allow") return this.addFolder(action.dataset.path);
    if (name === "retry") return this.openRoot(this.current);
    if (name === "pick") {
      const form = action.closest("form");
      return pickFolder(form.elements.path).then((path) => (path ? this.addFolder(path, form.querySelector("[data-ce-error]")) : null));
    }
    return undefined;
  }

  submitted(event) {
    const form = event.target.closest("[data-ce-add]");
    if (!form) return;
    event.preventDefault();
    const error = form.querySelector("[data-ce-error]");
    error.hidden = true;
    const path = form.elements.path.value.trim();
    if (path) this.addFolder(path, error);
  }

  quickOpen() {
    if (this.current && !this.bodyWrap.hidden) openQuickOpen(this.current, (rel) => this.openFile(rel, { user: true }));
  }

  key(event) {
    if (!this.root.isConnected) return;
    const quick = event.key.toLowerCase() === "p" && (isMac ? event.metaKey && !event.shiftKey : event.ctrlKey && event.shiftKey);
    if (quick) {
      event.preventDefault();
      event.stopImmediatePropagation();  // outside the Mac this same shortcut opens Prompts on the other screens
      this.quickOpen();
      return;
    }
    const mod = isMac ? event.metaKey : event.ctrlKey;
    if (!mod || event.key.toLowerCase() !== "f" || !this.viewer.editor || !this.root.isConnected || this.viewer.hasFocus()) return;
    event.preventDefault();
    this.viewer.search();
  }

  /** Same screen, other folder or file: no remount. */
  reveal(route) {
    if (route.root && route.root !== this.current) return this.openRoot(route.root, route.file, route.line);
    if (!route.root && !this.current) return this.start();
    if (route.file && route.file !== this.viewer.path) return this.openFile(route.file, { line: route.line });
    if (route.file && route.line && this.viewer.editor && this.viewer.editor.line) this.viewer.editor.line(route.line);
    return undefined;
  }

  destroy() {
    this.destroyed = true;
    document.removeEventListener("keydown", this.onKey, true);
    this.stopRoot();
    this.follow.destroy();
    this.viewer.destroy();
    setWindowTitle("");
  }
}
