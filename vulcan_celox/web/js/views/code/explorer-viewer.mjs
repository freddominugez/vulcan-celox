// Viewer of the Code screen: one file or its diff against git. The content is data: it goes in as the editor document.

import { ApiError, get, post } from "../../api.mjs";
import { esc, icon, reportError } from "../../dom.mjs";
import { t } from "../../i18n.mjs";
import { loadCodeMirror, mountDiff, mountFile, openSearch, updateFile } from "./code-editor.mjs";
import { changedLines } from "./code-live.mjs";
import { diffNotes, REASONS, searchPhrases } from "./code-text.mjs";

const LAYOUT = "vulcan-code-layout";

function savedLayout() {
  try { return localStorage.getItem(LAYOUT) === "unified" ? "unified" : "split"; } catch (_) { return "split"; }
}

export const query = (params) => Object.entries(params).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");

function segmented(label, options, current, attr) {
  return `<div class="segmented" role="group" aria-label="${esc(label)}">${options.map(([id, text]) =>
    `<button type="button" class="seg ${id === current ? "is-on" : ""}" ${attr}="${id}" aria-pressed="${id === current}">${esc(text)}</button>`).join("")}</div>`;
}

export class ExplorerViewer {
  constructor(host) {
    host.innerHTML = `<div class="code-bar"></div><div class="code-notes"></div><div class="code-body"></div>`;
    this.bar = host.querySelector(".code-bar");
    this.notes = host.querySelector(".code-notes");
    this.body = host.querySelector(".code-body");
    this.root = null;
    this.path = null;
    this.mode = "file";
    this.layout = savedLayout();
    this.editor = null;
    this.ticket = 0;
    host.addEventListener("click", (e) => this.clicked(e));
  }

  reset(root) {
    this.ticket += 1;
    this.root = root;
    this.path = null;
    this.mode = "file";
    this.bar.innerHTML = "";
    this.clear();
  }

  clear() {
    if (this.editor) this.editor.destroy();
    this.editor = null;
    this.body.innerHTML = "";
    this.notes.innerHTML = "";
  }

  message(title, text, extra = "") {
    this.clear();
    this.body.innerHTML = `<div class="code-empty"><h3>${esc(title)}</h3><p>${esc(text)}</p>${extra}</div>`;
  }

  /** Why a file does not show. Each case explains and offers the next step. */
  refused(reason) {
    const [title, text] = reason === "outside"
      ? [t("Link para fora da pasta"), t("O visor só abre arquivos dentro da pasta aberta. Links para fora não são seguidos.")]
      : REASONS[reason] || [t("Não foi possível mostrar"), t("Tente outro arquivo.")];
    const next = ["too_large", "binary", "unreadable"].includes(reason)
      ? `<button type="button" class="btn btn-sm" data-ce-view="editor">${icon("external")}<span>${t("Abrir no editor")}</span></button>` : "";
    this.message(title, text, next);
    // what the viewer refuses by name or for being outside the folder is not offered to an editor either
    if (reason === "sensitive" || reason === "outside") {
      const button = this.bar.querySelector("[data-ce-view=editor]");
      if (button) button.remove();
    }
  }

  renderBar() {
    if (!this.path) {
      this.bar.innerHTML = "";
      return;
    }
    this.bar.innerHTML = `<span class="code-path mono" title="${esc(this.path)}">${esc(this.path)}</span>
      ${segmented(t("O que mostrar"), [["file", t("Arquivo")], ["diff", t("Diff contra o Git")]], this.mode, "data-ce-mode")}
      ${this.mode === "diff" ? segmented(t("Disposição"), [["split", t("Lado a lado")], ["unified", t("Unificado")]], this.layout, "data-ce-layout") : ""}
      <span class="spacer"></span>
      <button type="button" class="btn btn-sm" data-ce-view="editor">${icon("external")}<span>${t("Abrir no editor")}</span></button>`;
  }

  async open(rel, { line = 0 } = {}) {
    const ticket = ++this.ticket;
    this.path = rel;
    this.renderBar();
    let CM;
    try {
      CM = await loadCodeMirror();
    } catch (_) {
      this.message(t("Visor indisponível"), t("o visor de código não carregou"));
      return;
    }
    if (ticket !== this.ticket || this.destroyed) return;
    this.CM = CM;
    if (this.mode === "diff") await this.showDiff(ticket);
    else await this.showFile(ticket, line);
  }

  async showFile(ticket, line) {
    let data;
    try {
      data = await get(`/api/files/read?${query({ root: this.root, path: this.path })}`);
    } catch (err) {
      if (ticket !== this.ticket) return;
      if (!(err instanceof ApiError)) return reportError(err);
      this.refused((err.data && err.data.reason) || "unreadable");
      return;
    }
    if (ticket !== this.ticket || this.destroyed) return;
    this.stale = false;
    this.clear();
    if (data.lossy) this.notes.innerHTML = `<p class="code-note">${icon("info")}<span>${t("O arquivo não está em UTF-8; alguns caracteres aparecem trocados.")}</span></p>`;
    this.editor = mountFile(this.CM, this.body, data.text, data.language, searchPhrases());
    this.editor.kind = "file";
    if (line) this.editor.line(line);
  }

  async showDiff(ticket) {
    let data;
    try {
      data = await get(`/api/files/diff?${query({ root: this.root, path: this.path })}`);
    } catch (err) {
      if (ticket !== this.ticket) return;
      if (!(err instanceof ApiError)) return reportError(err);
      this.refused((err.data && err.data.reason) || "unreadable");
      return;
    }
    if (ticket !== this.ticket || this.destroyed) return;
    const back = `<button type="button" class="btn btn-sm" data-ce-mode="file">${t("Ver o arquivo")}</button>`;
    if (!data.available) {
      const [title, text] = REASONS[data.reason] || [t("Não foi possível mostrar"), t("Tente outro arquivo.")];
      this.message(title, text, back);
      return;
    }
    if (data.old === data.new) {
      this.message(t("Sem diferença"), t("O arquivo está igual ao último commit."), back);
      return;
    }
    this.clear();
    this.notes.innerHTML = diffNotes(data, "git");
    this.editor = mountDiff(this.CM, this.body, { old: data.old, current: data.new, language: data.language, layout: this.layout, phrases: searchPhrases() });
    this.editor.kind = "diff";
  }

  /** The open file changed on disk. A failed read here is a write in progress: the next round tries again, with no error on screen. */
  async refresh({ reveal = false } = {}) {
    if (!this.path) return;
    const editing = this.editor && this.editor.kind === "file";
    if (!editing) {
      const scroller = this.body.querySelector(".cm-scroller");
      const top = scroller ? scroller.scrollTop : 0;
      await this.open(this.path);
      const again = this.body.querySelector(".cm-scroller");
      if (again) again.scrollTop = top;
      return;
    }
    const ticket = this.ticket;
    let data;
    try {
      data = await get(`/api/files/read?${query({ root: this.root, path: this.path })}`);
    } catch (err) {
      if (ticket !== this.ticket || !(err instanceof ApiError) || !err.data) return;
      if (err.data.reason === "missing") this.deletedNote();
      else if (err.data.reason !== "changing") this.note(err.data.reason);
      this.stale = err.data.reason === "changing";
      return;
    }
    if (ticket !== this.ticket || this.destroyed || !this.editor || this.editor.kind !== "file") return;
    this.stale = false;
    this.notes.innerHTML = "";
    const old = this.editor.editor.state.doc.toString();
    updateFile(this.CM, this.editor, data.text, changedLines(old, data.text), { reveal });
  }

  /** Can this file be followed? Only readable text: a refused one does not take the viewer away from where it is. */
  async readable(rel) {
    try {
      await get(`/api/files/read?${query({ root: this.root, path: rel })}`);
      return true;
    } catch (_) {
      return false;
    }
  }

  /** Keeps the last content in view and says so. */
  deletedNote() {
    this.notes.innerHTML = `<p class="code-note ce-gone">${icon("alert")}<span>${t("Este arquivo foi apagado. O último conteúdo continua à vista.")}</span></p>`;
  }

  note(reason) {
    const entry = REASONS[reason];
    if (entry) this.notes.innerHTML = `<p class="code-note ce-gone">${icon("alert")}<span>${esc(entry[0])}. ${esc(entry[1])}</span></p>`;
  }

  clicked(event) {
    const mode = event.target.closest("[data-ce-mode]");
    if (mode) {
      this.mode = mode.dataset.ceMode;
      if (this.path) this.open(this.path);
      return;
    }
    const layout = event.target.closest("[data-ce-layout]");
    if (layout) {
      this.layout = layout.dataset.ceLayout;
      try { localStorage.setItem(LAYOUT, this.layout); } catch (_) { /* no storage: applies only now */ }
      if (this.path) this.open(this.path);
      return;
    }
    if (event.target.closest("[data-ce-view=editor]")) {
      post("/api/open", { kind: "code_file", root: this.root, target: this.path }).catch(reportError);
    }
  }

  search() {
    if (this.editor) openSearch(this.CM, this.editor);
  }

  hasFocus() {
    return this.body.contains(document.activeElement);
  }

  destroy() {
    this.destroyed = true;
    this.ticket += 1;
    this.clear();
  }
}
