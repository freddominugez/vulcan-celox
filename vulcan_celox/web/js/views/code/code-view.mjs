// Agent session Código tab: tree, file and diff. Read-only. Stays mounted while the session is open, so the
// automatic update does not wipe the viewer's selection or scroll.

import { ApiError, get, isMac, post } from "../../api.mjs";
import { esc, icon, reportError } from "../../dom.mjs";
import { t } from "../../i18n.mjs";
import { Follow } from "./code-follow.mjs";
import { diffNotes, REASONS, searchPhrases } from "./code-text.mjs";
import { loadCodeMirror, mountDiff, mountFile, openSearch } from "./code-editor.mjs";
import { renderTree } from "./code-tree.mjs";

const SCOPES = [["edit", t("Edição")], ["turn", t("Turno")], ["git", "Git"]];
const LAYOUT_KEY = "vulcan-code-layout";

function savedLayout() {
  try { return localStorage.getItem(LAYOUT_KEY) === "unified" ? "unified" : "split"; } catch (_) { return "split"; }
}

function segmented(label, options, current, attr) {
  return `<div class="segmented" role="group" aria-label="${esc(label)}">${options.map(([id, text]) =>
    `<button type="button" class="seg ${id === current ? "is-on" : ""}" ${attr}="${id}" aria-pressed="${id === current}">${esc(text)}</button>`).join("")}</div>`;
}

export class CodeView {
  constructor(session, target = null) {
    this.session = session;
    this.target = target;  // file and line requested by the click in the terminal
    this.el = document.createElement("div");
    this.el.className = "code-shell";
    this.el.innerHTML = `<nav class="code-side" aria-label="${t("Arquivos da sessão")}"></nav>
      <section class="code-main" aria-label="${t("Visor de código")}"><div class="code-bar"></div><div class="code-follow"></div><div class="code-notes"></div><div class="code-body"></div></section>`;
    this.side = this.el.querySelector(".code-side");
    this.bar = this.el.querySelector(".code-bar");
    this.notes = this.el.querySelector(".code-notes");
    this.followEl = this.el.querySelector(".code-follow");
    this.follow = null;
    this.bodyEl = this.el.querySelector(".code-body");
    this.tree = null;
    this.path = null;
    this.mode = "file";
    this.scope = "edit";
    this.seq = null;
    this.layout = savedLayout();
    this.edits = [];
    this.viewer = null;
    this.ticket = 0;
    this.followTurn = 0;
    this.el.addEventListener("click", (e) => this.onClick(e));
    // only user gestures pause; scrolling done by the viewer itself triggers none of these
    this.onGesture = (e) => { if (!e.target.closest("[data-code=resume]")) this.interacted(); };
    this.el.addEventListener("pointerdown", this.onGesture);
    this.bodyEl.addEventListener("wheel", this.onGesture, { passive: true });
    this.bodyEl.addEventListener("keydown", this.onGesture);
    this.onKey = (e) => this.key(e);
    document.addEventListener("keydown", this.onKey);
    this.update();
  }

  /** Called on open and on every index change. */
  async update(session) {
    if (session) this.session = session;
    let tree;
    try {
      tree = await get(`/api/code/session/${encodeURIComponent(this.session.id)}/tree`);
    } catch (err) {
      reportError(err);
      return;
    }
    if (this.destroyed) return;
    const first = !this.tree;
    if (this.extra && !tree.files.some((f) => f.path === this.extra.path)) tree.files.push(this.extra);
    this.tree = tree;
    if (first) this.follow = new Follow(tree.is_active, tree.last_seq);
    this.follow.setActive(tree.is_active);
    this.renderSide();
    const go = this.follow.next(tree.last_seq);
    if (first) await this.start();
    else if (go || (!this.path && tree.files.length)) await this.followLatest();
    this.renderFollow();
  }

  async start() {
    if (this.tree.root_refused) return this.empty("root_refused");
    const files = this.tree.files;
    const wanted = this.target && this.target.path;
    if (wanted) {
      this.follow.userInteracted();  // whoever clicked wants to read this range, not follow the agent
      if (!files.some((f) => f.path === wanted)) {
        this.extra = this.extraFile(wanted);
        this.tree.files = [...files, this.extra];
        this.renderSide();
      }
      if (this.target.seq) {  // coming from a Linha do tempo request: that request's diff
        this.scope = "turn";
        await this.select(wanted, "diff", this.target.seq);
      } else {
        await this.select(wanted, "file");
        if (this.viewer && this.viewer.line) this.viewer.line(this.target.line);
      }
      this.target = null;
      return undefined;
    }
    if (!files.length) {
      return this.emptyText(t("Nenhum arquivo ainda"), t("Esta sessão ainda não tocou em nenhum arquivo. A árvore aparece aqui quando ela tocar."));
    }
    await this.select((this.latest() || files[0]).path);
    return this.revealLatest();
  }

  /** File clicked in the terminal that the session did not touch: the server still decides whether to open it. */
  extraFile(path) {
    const root = this.tree.root.replace(/\/$/, "");
    const rel = path.startsWith(`${root}/`) ? path.slice(root.length + 1) : path;
    return { path, rel, kind: "read", inside: true, exists: true, sensitive: false, edits: 0, last_seq: 0, failed: 0, language: "" };
  }

  /** The last edited file the viewer can open. */
  latest() {
    const files = this.tree.files.filter((f) => f.inside && !f.sensitive);
    return files.sort((a, b) => b.last_seq - a.last_seq)[0];
  }

  following() {
    return this.follow && this.follow.state === "following" && !this.destroyed;
  }

  /** Goes to the newest edit. After each wait it checks again: the user may have paused midway. */
  async followLatest() {
    const latest = this.latest();
    if (!latest) return;
    const turn = ++this.followTurn;
    this.seq = null;
    if (latest.path !== this.path) {
      this.path = latest.path;
      this.renderSide();
      await this.loadEdits();
      if (turn !== this.followTurn || !this.followingOrFirst()) return;
      await this.show();
    } else {
      await this.loadEdits();
      if (this.viewer && this.viewer.kind === "file") await this.refreshFile(turn);
      else await this.show();
    }
    if (turn === this.followTurn) await this.revealLatest();
  }

  followingOrFirst() {
    return this.following() || (this.follow && this.follow.state === "off");
  }

  /** Updates the text in the same editor, without losing the position. */
  async refreshFile(turn) {
    try {
      const data = await get(`/api/code/file?session=${encodeURIComponent(this.session.id)}&path=${encodeURIComponent(this.path)}`);
      if (turn === this.followTurn && this.following() && this.viewer && this.viewer.setText) this.viewer.setText(data.text);
    } catch (err) {
      if (turn === this.followTurn && this.following()) await this.show();  // deleted or refused: shows the empty state
    }
  }

  /** Scrolls to the range of the last edit of the open file. */
  async revealLatest() {
    const file = this.file();
    if (!this.following() || !file || !file.edits || !this.viewer || this.viewer.kind !== "file") return;
    try {
      const data = await get(`/api/code/session/${encodeURIComponent(this.session.id)}/diff?path=${encodeURIComponent(this.path)}&scope=edit`);
      if (this.following() && data.available && this.viewer && this.viewer.reveal) this.viewer.reveal(data.new);
    } catch (_) { /* without the range: stays at the top of the file */ }
  }

  interacted() {
    if (!this.follow) return;
    const was = this.follow.state;
    this.follow.userInteracted();
    if (was !== this.follow.state) this.renderFollow();
  }

  renderFollow() {
    const state = this.follow ? this.follow.state : "off";
    this.followEl.className = `code-follow is-${state}`;
    if (state === "following") this.followEl.innerHTML = `<span class="code-follow-dot"></span><span>${t("Seguindo o agente")}</span>`;
    else if (state === "paused") {
      this.followEl.innerHTML = `<span>${t("Pausado: o visor não muda enquanto você lê.")}</span>
        <button type="button" class="btn btn-sm" data-code="resume">${icon("play")}<span>${t("Voltar a seguir")}</span></button>`;
    } else this.followEl.innerHTML = "";
  }

  file() {
    return this.tree && this.tree.files.find((f) => f.path === this.path);
  }

  renderSide() {
    const top = this.side.scrollTop;
    this.side.innerHTML = renderTree(this.tree.files, this.path);
    this.side.scrollTop = top;
  }

  async select(path, mode, seq = null) {
    this.path = path;
    this.seq = seq;
    if (mode) this.mode = mode;
    this.renderSide();
    await this.loadEdits();
    return this.show();
  }

  async loadEdits() {
    const file = this.file();
    if (!file || !file.edits) {
      this.edits = [];
      return;
    }
    try {
      const data = await get(`/api/code/session/${encodeURIComponent(this.session.id)}/edits?limit=500&path=${encodeURIComponent(this.path)}`);
      this.edits = data.edits;
    } catch (err) {
      this.edits = [];
    }
  }

  renderBar(info = {}) {
    const file = this.file();
    if (!file) {
      this.bar.innerHTML = "";
      return;
    }
    const position = this.edits.findIndex((r) => r.seq === info.seq);
    const stepper = this.mode === "diff" && this.scope !== "git" && this.edits.length > 1 && position >= 0
      ? `<span class="code-step"><button type="button" class="btn btn-ghost btn-sm" data-step="-1" ${position === 0 ? "disabled" : ""} aria-label="${t("Edição anterior")}">${icon("chevron-left")}</button>
         <span class="dim">${t("Edição {n} de {total}", { n: position + 1, total: this.edits.length })}</span>
         <button type="button" class="btn btn-ghost btn-sm" data-step="1" ${position === this.edits.length - 1 ? "disabled" : ""} aria-label="${t("Próxima edição")}">${icon("chevron-right")}</button></span>` : "";
    this.bar.innerHTML = `<span class="code-path mono" title="${esc(file.path)}">${esc(file.rel)}</span>
      ${segmented(t("O que mostrar"), [["file", t("Arquivo")], ["diff", "Diff"]], this.mode, "data-mode")}
      ${this.mode === "diff" ? segmented(t("Comparar com"), SCOPES, this.scope, "data-scope") : ""}
      ${stepper}
      ${this.mode === "diff" ? segmented(t("Disposição"), [["split", t("Lado a lado")], ["unified", t("Unificado")]], this.layout, "data-layout") : ""}
      <span class="spacer"></span>
      ${file.inside && !file.sensitive && file.exists ? `<button type="button" class="btn btn-sm" data-code="open">${icon("external")}<span>${t("Abrir no editor")}</span></button>` : ""}`;
  }

  clearViewer() {
    if (this.viewer) this.viewer.destroy();
    this.viewer = null;
    this.bodyEl.innerHTML = "";
    this.notes.innerHTML = "";
  }

  emptyText(title, text, extra = "") {
    this.clearViewer();
    this.bodyEl.innerHTML = `<div class="code-empty"><h3>${esc(title)}</h3><p>${esc(text)}</p>${extra}</div>`;
  }

  empty(reason, extra = "") {
    const [title, text] = REASONS[reason] || [t("Não foi possível mostrar"), t("Tente outro arquivo.")];
    this.emptyText(title, text, extra);
  }

  async show() {
    const ticket = ++this.ticket;
    const file = this.file();
    if (!file) return;
    if (this.mode === "diff" && !file.edits && this.scope !== "git") this.scope = "git";
    this.renderBar();
    let CM;
    try {
      CM = await loadCodeMirror();
    } catch (err) {
      this.emptyText(t("Visor indisponível"), t("o visor de código não carregou"));
      return;
    }
    if (ticket !== this.ticket || this.destroyed) return;
    this.CM = CM;
    if (this.mode === "diff") await this.showDiff(CM, ticket);
    else await this.showFile(CM, ticket);
  }

  async showFile(CM, ticket) {
    let data;
    try {
      data = await get(`/api/code/file?session=${encodeURIComponent(this.session.id)}&path=${encodeURIComponent(this.path)}`);
    } catch (err) {
      if (ticket !== this.ticket) return;
      if (!(err instanceof ApiError)) return reportError(err);
      const hasEdits = err.data && err.data.reason === "missing" && this.file().edits;
      this.empty((err.data && err.data.reason) || "unreadable",
        hasEdits ? `<button type="button" class="btn btn-sm" data-mode="diff">${t("Ver a última edição")}</button>` : "");
      return;
    }
    if (ticket !== this.ticket || this.destroyed) return;
    this.clearViewer();
    if (data.lossy) this.notes.innerHTML = `<p class="code-note">${icon("info")}<span>${t("O arquivo não está em UTF-8; alguns caracteres aparecem trocados.")}</span></p>`;
    this.viewer = mountFile(CM, this.bodyEl, data.text, data.language, searchPhrases());
    this.viewer.kind = "file";
  }

  async showDiff(CM, ticket) {
    const seq = this.seq ? `&seq=${this.seq}` : "";
    let data;
    try {
      data = await get(`/api/code/session/${encodeURIComponent(this.session.id)}/diff?path=${encodeURIComponent(this.path)}&scope=${this.scope}${seq}`);
    } catch (err) {
      if (ticket !== this.ticket) return;
      if (!(err instanceof ApiError)) return reportError(err);
      this.empty((err.data && err.data.reason) || "unreadable");
      return;
    }
    if (ticket !== this.ticket || this.destroyed) return;
    this.renderBar(data);
    if (!data.available) return this.empty(data.reason);
    if (data.old === data.new) {
      return this.emptyText(t("Sem diferença"), this.scope === "git" ? t("O arquivo está igual ao último commit.") : t("Esta edição não mudou o texto."));
    }
    this.clearViewer();
    this.notes.innerHTML = diffNotes(data, this.scope);
    this.viewer = mountDiff(CM, this.bodyEl, { old: data.old, current: data.new, language: data.language, layout: this.layout, phrases: searchPhrases() });
    this.viewer.kind = "diff";
  }

  onClick(event) {
    // via keyboard the button gets a click without pointerdown: choosing a file or mode also pauses
    if (event.target.closest("button") && !event.target.closest("[data-code]")) this.interacted();
    const pick = event.target.closest("[data-path]");
    if (pick) return this.select(pick.dataset.path);
    const mode = event.target.closest("[data-mode]");
    if (mode) {
      this.mode = mode.dataset.mode;
      return this.show();
    }
    const scope = event.target.closest("[data-scope]");
    if (scope) {
      this.scope = scope.dataset.scope;
      return this.show();
    }
    const layout = event.target.closest("[data-layout]");
    if (layout) {
      this.layout = layout.dataset.layout;
      try { localStorage.setItem(LAYOUT_KEY, this.layout); } catch (_) { /* no storage: applies only now */ }
      return this.show();
    }
    const step = event.target.closest("[data-step]");
    if (step) {
      const at = this.edits.findIndex((r) => r.seq === (this.seq || this.edits[this.edits.length - 1].seq));
      const next = this.edits[at + Number(step.dataset.step)];
      if (next) {
        this.seq = next.seq;
        this.show();
      }
      return undefined;
    }
    if (event.target.closest("[data-code=resume]")) {
      this.follow.resume();
      this.renderFollow();
      return this.followLatest();
    }
    if (event.target.closest("[data-code=open]")) {
      post("/api/open", { kind: "session_file", session: this.session.id, target: this.path }).catch(reportError);
    }
    return undefined;
  }

  /** ⌘F opens the viewer search even with focus outside it. */
  key(event) {
    const mod = isMac ? event.metaKey : event.ctrlKey;
    if (!mod || event.key.toLowerCase() !== "f" || !this.el.isConnected || !this.viewer || this.bodyEl.contains(document.activeElement)) return;
    event.preventDefault();
    openSearch(this.CM, this.viewer);
  }

  /** The tab appeared again: the editor remeasures what was off screen. */
  attached() {
    if (this.viewer) this.viewer.editor.requestMeasure();
  }

  destroy() {
    this.destroyed = true;
    document.removeEventListener("keydown", this.onKey);
    this.followTurn += 1;
    if (this.viewer) this.viewer.destroy();
  }
}
