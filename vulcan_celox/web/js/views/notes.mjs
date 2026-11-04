// Sticky notes of a site (or Global): in-place editing, colors, pinning, tags and drag to reorder.

import { del, get, patch, post } from "../api.mjs";
import { $, debounce, flashFocus, esc, icon, reportError } from "../dom.mjs";
import { t } from "../i18n.mjs";

const COLOR_NAMES = { amarelo: t("Amarelo"), rosa: t("Rosa"), verde: t("Verde"), azul: t("Azul"), laranja: t("Laranja"), roxo: t("Roxo") };

export class NotesView {
  /** @param {{site: string|null, onChange: Function}} options */
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.query = "";
    this.scope = options.terminal ? "session" : "site";
    this.tag = "";
    this.notes = [];
    this.tags = [];
    this.colors = Object.keys(COLOR_NAMES);
    this.dragging = null;
    this.saveText = new Map();
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.root.addEventListener("input", (e) => this.onInput(e));
    this.root.addEventListener("keydown", (e) => this.onKey(e));
    // the card is only draggable while the handle is pressed (in WebKit, draggable prevents editing the text)
    this.root.addEventListener("pointerdown", (e) => {
      const grip = e.target.closest(".note-grip");
      if (grip) grip.closest(".note").setAttribute("draggable", "true");
    });
    this.root.addEventListener("pointerup", () => this.root.querySelectorAll(".note[draggable]").forEach((n) => n.removeAttribute("draggable")));
    this.root.addEventListener("dragstart", (e) => this.onDragStart(e));
    this.root.addEventListener("dragover", (e) => e.preventDefault());
    this.root.addEventListener("drop", (e) => this.onDrop(e));
    this.root.addEventListener("dragend", () => this.root.querySelectorAll(".is-dragging, .note[draggable]").forEach((n) => {
      n.classList.remove("is-dragging");
      n.removeAttribute("draggable");
    }));
    this.renderShell();
    this.load();
  }

  get siteParam() {
    return this.options.site || "";
  }

  get sessionScoped() {
    return Boolean(this.options.terminal) && this.scope === "session";
  }

  async load() {
    const params = new URLSearchParams({ site: this.siteParam });
    if (this.sessionScoped) params.set("terminal", this.options.terminal);
    if (this.query) params.set("q", this.query);
    if (this.tag) params.set("tag", this.tag);
    try {
      const [data, tags] = await Promise.all([get(`/api/notes?${params}`), get("/api/tags")]);
      if (!this.root.isConnected) return; // the screen was switched while loading
      this.notes = data.notes;
      this.colors = data.colors;
      this.tags = tags.tags;
      this.renderGrid();
    } catch (err) {
      reportError(err);
    }
  }

  renderShell() {
    this.root.innerHTML = `
      <div class="notes">
        <div class="notes-bar">
          <button class="btn btn-primary" data-action="new-note">${icon("plus")}<span>${t("Novo post-it")}</span></button>
          ${this.options.terminal ? `<div class="segmented" role="tablist" aria-label="${t("Escopo")}">
            <button type="button" class="seg ${this.scope === "session" ? "is-on" : ""}" data-scope="session" title="${t("Só o que foi criado nesta sessão de terminal")}">${icon("terminal")}<span>${t("Esta sessão")}</span></button>
            <button type="button" class="seg ${this.scope === "site" ? "is-on" : ""}" data-scope="site">${this.options.site ? t("Todo o site") : t("Todo o Global")}</button>
          </div>` : ""}
          <label class="search-field">${icon("search")}<input data-role="query" placeholder="${t("Buscar nos post-its")}" aria-label="${t("Buscar nos post-its")}"></label>
          <select class="select select-sm" data-role="tag" aria-label="${t("Filtrar por tag")}"><option value="">${t("Todas as tags")}</option></select>
          <div class="spacer"></div>
          <span class="dim hint">${t("Salva sozinho · arraste para reordenar")}</span>
        </div>
        <div class="note-grid" data-role="grid"></div>
      </div>`;
    $("[data-role=tag]", this.root).addEventListener("change", (e) => {
      this.tag = e.target.value;
      this.load();
    });
    $("[data-role=query]", this.root).addEventListener("input", debounce((e) => {
      this.query = e.target.value.trim();
      this.load();
    }, 200));
  }

  renderGrid() {
    const tagSelect = $("[data-role=tag]", this.root);
    tagSelect.innerHTML = `<option value="">${t("Todas as tags")}</option>` +
      this.tags.map((tag) => `<option value="${tag.id}" ${tag.id === this.tag ? "selected" : ""}>${esc(tag.name)}</option>`).join("");
    const grid = $("[data-role=grid]", this.root);
    if (!this.notes.length) {
      grid.innerHTML = `<div class="empty-inline">${icon("note")}<span>${this.query || this.tag
        ? t("Nenhum post-it encontrado com esse filtro.")
        : this.sessionScoped ? t("Nenhum post-it nesta sessão. Os que você criar aqui entram na memória de “{title}”.", { title: esc(this.options.sessionTitle) })
        : t("Nenhum post-it ainda. Use “Novo post-it” para anotar comandos, credenciais de teste ou lembretes do projeto.")}</span></div>`;
      return;
    }
    grid.innerHTML = this.notes.map((n) => `
      <article class="note note-${n.color} ${n.pinned ? "is-pinned" : ""}" data-id="${n.id}">
        <header class="note-head">
          <span class="note-grip" title="${t("Arraste para reordenar")}">${icon("grip")}</span>
          <button class="icon-btn icon-btn-sm ${n.pinned ? "is-on" : ""}" data-action="pin" aria-label="${n.pinned ? t("Desafixar") : t("Fixar no topo")}" title="${n.pinned ? t("Desafixar") : t("Fixar no topo")}">${icon("pin")}</button>
          <div class="note-colors" role="group" aria-label="${t("Cor")}">
            ${this.colors.map((c) => `<button class="swatch swatch-${c} ${c === n.color ? "is-on" : ""}" data-action="color" data-color="${c}" aria-label="${COLOR_NAMES[c] || c}" title="${COLOR_NAMES[c] || c}"></button>`).join("")}
          </div>
          <div class="spacer"></div>
          <button class="icon-btn icon-btn-sm" data-action="delete" aria-label="${t("Apagar post-it")}">${icon("trash")}</button>
        </header>
        <textarea class="note-text" rows="5" placeholder="${t("Escreva aqui…")}" aria-label="${t("Texto do post-it")}">${esc(n.text)}</textarea>
        ${n.terminal_title && !this.sessionScoped ? `<div class="note-session">${icon("terminal")}${esc(n.terminal_title)}</div>` : ""}
        <footer class="note-foot">
          ${n.chips.map((c) => `<span class="chip" style="--chip:${esc(c.color)}">${esc(c.name)}<button class="chip-x" data-action="untag" data-tag="${c.id}" aria-label="${t("Remover tag {name}", { name: esc(c.name) })}">${icon("x")}</button></span>`).join("")}
          <input class="note-tag-input" data-role="add-tag" placeholder="${t("+ tag")}" list="note-tag-options" aria-label="${t("Adicionar tag")}">
        </footer>
      </article>`).join("") + `<datalist id="note-tag-options">${this.tags.map((t) => `<option value="${esc(t.name)}">`).join("")}</datalist>`;
    grid.querySelectorAll(".note-text").forEach((ta) => this.autosize(ta));
    const card = flashFocus(grid, this.options, (id) => `.note[data-id="${id}"]`);
    const text = card && card.querySelector(".note-text");
    if (text && !text.value) text.focus(); // new sticky note created from the session menu: ready to type
  }

  autosize(textarea) {
    textarea.style.height = "auto";
    textarea.style.height = `${Math.max(96, textarea.scrollHeight)}px`;
  }

  note(el) {
    const card = el.closest(".note");
    return card ? this.notes.find((n) => n.id === card.dataset.id) : null;
  }

  onInput(event) {
    if (!event.target.classList.contains("note-text")) return;
    const note = this.note(event.target);
    if (!note) return;
    this.autosize(event.target);
    note.text = event.target.value;
    if (!this.saveText.has(note.id)) {
      this.saveText.set(note.id, debounce((id, text) => patch(`/api/notes/${id}`, { text }).catch(reportError), 600));
    }
    this.saveText.get(note.id)(note.id, note.text);
  }

  async onKey(event) {
    if (event.target.dataset.role !== "add-tag" || event.key !== "Enter") return;
    event.preventDefault();
    const note = this.note(event.target);
    const name = event.target.value.trim();
    if (!note || !name) return;
    try {
      await patch(`/api/notes/${note.id}`, { tags: [...note.chips.map((c) => c.id), name] });
      await this.load();
    } catch (err) {
      reportError(err);
    }
  }

  async onClick(event) {
    const scope = event.target.closest("[data-scope]");
    if (scope) {
      this.scope = scope.dataset.scope;
      this.root.querySelectorAll("[data-scope]").forEach((b) => b.classList.toggle("is-on", b === scope));
      this.load();
      return;
    }
    const target = event.target.closest("[data-action]");
    if (!target) return;
    const action = target.dataset.action;
    try {
      if (action === "new-note") {
        const note = await post("/api/notes", { site: this.siteParam, text: "", tags: this.tag ? [this.tag] : [],
          terminal: this.sessionScoped ? this.options.terminal : null });
        await this.load();
        const ta = this.root.querySelector(`.note[data-id="${note.id}"] .note-text`);
        if (ta) ta.focus();
        this.options.onChange();
        return;
      }
      const note = this.note(target);
      if (!note) return;
      if (this.saveText.has(note.id)) this.saveText.get(note.id).flush(note.id, note.text);
      if (action === "pin") await patch(`/api/notes/${note.id}`, { pinned: !note.pinned });
      if (action === "color") await patch(`/api/notes/${note.id}`, { color: target.dataset.color });
      if (action === "untag") await patch(`/api/notes/${note.id}`, { tags: note.chips.map((c) => c.id).filter((id) => id !== target.dataset.tag) });
      if (action === "delete") {
        await del(`/api/notes/${note.id}`);
        this.options.onChange();
      }
      await this.load();
    } catch (err) {
      reportError(err);
    }
  }

  onDragStart(event) {
    const card = event.target.closest(".note");
    if (!card || event.target.closest("textarea, input")) return;
    this.dragging = card.dataset.id;
    card.classList.add("is-dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", card.dataset.id);
  }

  async onDrop(event) {
    event.preventDefault();
    const card = event.target.closest(".note");
    if (!card || !this.dragging || card.dataset.id === this.dragging) return;
    try {
      // position relative to another note: the index in the filtered list (session, search, tag) is not valid for the whole site
      await post(`/api/notes/${this.dragging}/move`, { target: card.dataset.id });
      this.dragging = null;
      await this.load();
    } catch (err) {
      reportError(err);
    }
  }

  destroy() {
    this.saveText.forEach((fn, id) => {
      const note = this.notes.find((n) => n.id === id);
      if (note) fn.flush(id, note.text);
    });
  }
}
