// Tags de uma sessão de terminal: as da própria sessão e os itens da sessão agrupados por tag.

import { get, patch } from "../api.mjs";
import { $, esc, flashFocus, icon, reportError } from "../dom.mjs";
import { t } from "../i18n.mjs";

export class SessionTagsView {
  /** @param {{sessionId: string, onChange: Function}} options */
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.session = null;
    this.tags = [];
    this.tasks = [];
    this.notes = [];
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.root.addEventListener("keydown", (e) => this.onKey(e));
    this.load();
  }

  async load() {
    const id = this.options.sessionId;
    try {
      const [session, tags, tasks, notes] = await Promise.all([
        get(`/api/sessions/${id}`), get("/api/tags"),
        get(`/api/tasks?site=*&terminal=${id}`), get(`/api/notes?site=*&terminal=${id}`),
      ]);
      this.session = session;
      this.tags = tags.tags;
      this.tasks = tasks.tasks;
      this.notes = notes.notes;
      if (!this.root.isConnected) return; // a tela foi trocada enquanto carregava
      this.render();
    } catch (err) {
      reportError(err);
    }
  }

  render() {
    const s = this.session;
    const chips = s.tags.map((tg) => `<span class="chip chip-lg" data-tag="${esc(tg.id)}" style="--chip:${esc(tg.color)}">${esc(tg.name)}
      <button class="chip-x" data-action="remove" data-tag="${tg.id}" aria-label="${t("Remover tag {name}", { name: esc(tg.name) })}">${icon("x")}</button></span>`).join("");

    const groups = new Map();
    const push = (key, entry) => {
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(entry);
    };
    for (const task of this.tasks) {
      if (task.chips.length) task.chips.forEach((c) => push(c.id, { kind: "task", item: task }));
      else push("", { kind: "task", item: task });
    }
    for (const note of this.notes) {
      if (note.chips.length) note.chips.forEach((c) => push(c.id, { kind: "note", item: note }));
      else push("", { kind: "note", item: note });
    }
    const tagById = new Map(this.tags.map((t) => [t.id, t]));
    const ordered = [...groups.keys()].sort((a, b) => {
      if (!a) return 1;
      if (!b) return -1;
      return (tagById.get(a)?.name || "").localeCompare(tagById.get(b)?.name || "");
    });
    const sections = ordered.map((key) => {
      const tag = tagById.get(key);
      const entries = groups.get(key);
      const rows = entries.map(({ kind, item }) => kind === "task"
        ? `<li class="tag-item status-${item.status}">${icon(item.status === "done" ? "circle-check" : item.status === "doing" ? "circle-half" : "circle")}<span>${esc(item.title)}</span><span class="dim">${t("tarefa")}</span></li>`
        : `<li class="tag-item">${icon("note")}<span>${esc(item.title || t("(post-it sem título)"))}</span><span class="dim">${t("post-it")}</span></li>`).join("");
      return `<section class="tag-group" data-tag="${esc(key)}">
          <h3>${tag ? `<span class="chip" style="--chip:${esc(tag.color)}">${esc(tag.name)}</span>` : `<span class="dim">${t("Sem tag")}</span>`}
            <span class="count">${entries.length}</span></h3>
          <ul>${rows}</ul>
        </section>`;
    }).join("");

    this.root.innerHTML = `
      <div class="session-tags">
        <div class="session-tags-head">
          <h2>${t("Tags desta sessão")}</h2>
          <p class="dim">${t("Marcam a sessão “{title}” no índice geral e na memória em Markdown.", { title: esc(s.title) })}</p>
          <div class="session-tag-row">
            ${chips || `<span class="dim">${t("Nenhuma tag ainda.")}</span>`}
            <input class="input input-tags" data-role="add" placeholder="${t("adicionar tag")}" list="session-tag-options" aria-label="${t("Adicionar tag à sessão")}">
            <datalist id="session-tag-options">${this.tags.map((t) => `<option value="${esc(t.name)}">`).join("")}</datalist>
          </div>
        </div>
        <div class="session-tags-body">
          <h2>${t("Itens da sessão por tag")}</h2>
          ${sections || `<div class="empty-inline">${icon("tag")}<span>${t("Esta sessão ainda não tem tarefas nem post-its. Crie nas abas Tarefas e Post-its.")}</span></div>`}
        </div>
      </div>`;
    flashFocus(this.root, this.options, (id) => `.tag-group[data-tag="${id}"], .session-tag-row .chip[data-tag="${id}"]`);
  }

  async save(tagIds) {
    try {
      await patch(`/api/sessions/${this.options.sessionId}`, { tags: tagIds });
      await this.load();
      this.options.onChange();
    } catch (err) {
      reportError(err);
    }
  }

  onKey(event) {
    if (event.target.dataset.role !== "add" || event.key !== "Enter") return;
    event.preventDefault();
    const name = event.target.value.trim();
    if (!name) return;
    this.save([...this.session.tags.map((t) => t.id), name]).then(() => {
      const input = $("[data-role=add]", this.root);
      if (input) input.focus();
    });
  }

  onClick(event) {
    const target = event.target.closest("[data-action=remove]");
    if (!target) return;
    this.save(this.session.tags.map((t) => t.id).filter((id) => id !== target.dataset.tag));
  }

  destroy() {}
}
