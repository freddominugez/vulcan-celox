// Tasks as a mini manager: assignee, due date, summary, filters and Lista or Quadro views (dragging changes the status).
import { del, get, patch, post } from "../api.mjs";
import { $, flashFocus, esc, formatDue, icon, progressBar, reportError, toast, todayISO } from "../dom.mjs";
import { t } from "../i18n.mjs";

const PRIORITY = { 1: t("Alta"), 2: t("Média"), 3: t("Baixa") };
const STATUS_LABEL = { todo: t("A fazer"), doing: t("Fazendo"), done: t("Feito") };
const FILTERS = [
  { id: "open", label: t("Abertas"), status: "todo,doing" },
  { id: "all", label: t("Todas"), status: "" },
  { id: "done", label: t("Concluídas"), status: "done" },
];
const DUE_FILTERS = [
  { id: "", label: t("Qualquer prazo") },
  { id: "late", label: t("Atrasadas") },
  { id: "today", label: t("Vencem hoje") },
  { id: "week", label: t("Próximos 7 dias") },
];
const NO_ASSIGNEE = "__sem__";
const AVATAR_COLORS = ["#6ea8fe", "#a78bfa", "#f472b6", "#2dd4bf", "#c4a484", "#93c5fd", "#e879f9", "#a1a1aa"];
const VIEW_KEY = "vulcan-tasks-view";

function initials(name) {
  const parts = name.trim().split(/\s+/);
  return ((parts[0] || "")[0] + (parts.length > 1 ? parts[parts.length - 1][0] : (parts[0] || "")[1] || "")).toUpperCase();
}

function avatarColor(name) {
  let hash = 0;
  for (const ch of name.toLowerCase()) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}

function avatar(name) {
  return `<span class="avatar" style="--avatar:${avatarColor(name)}" aria-hidden="true">${esc(initials(name))}</span>`;
}

/** Due date in management language: Hoje, Amanhã, Atrasada 3 d, weekday next week. */
function dueInfo(due, status) {
  if (!due) return null;
  const today = new Date(`${todayISO()}T00:00:00`);
  const date = new Date(`${due}T00:00:00`);
  const days = Math.round((date - today) / 86400000);
  if (status !== "done" && days < 0) return { text: t("Atrasada {n} d", { n: -days }), tone: "is-late" };
  if (days === 0) return { text: t("Hoje"), tone: status === "done" ? "" : "is-today" };
  if (days === 1) return { text: t("Amanhã"), tone: status === "done" ? "" : "is-soon" };
  if (days > 1 && days <= 6) {
    const weekday = [t("dom"), t("seg"), t("ter"), t("qua"), t("qui"), t("sex"), t("sáb")][date.getDay()];
    return { text: `${weekday}, ${formatDue(due)}`, tone: status === "done" ? "" : "is-soon" };
  }
  return { text: formatDue(due), tone: "" };
}

function readView() {
  try {
    return localStorage.getItem(VIEW_KEY) === "board" ? "board" : "list";
  } catch {
    return "list";
  }
}

export class TasksView {
  /** @param {{site: string|null|"*", sites: object[], onChange: Function, terminal?: string, sessionTitle?: string, focus?: string}} options */
  constructor(root, options) {
    this.root = root;
    this.options = options;
    // "nova": came from the session menu, cursor in the new-task field; another id: item opened from the tree (may be done)
    this.filter = options.focus && options.focus !== "nova" ? "all" : "open";
    this.scope = options.terminal ? "session" : "site";
    this.tag = "";
    this.sort = "priority";
    this.assignee = "";
    this.due = "";
    this.view = readView();
    this.tags = [];
    this.assignees = [];
    this.data = { tasks: [], progress: null, summary: null };
    this.dragging = null;
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.root.addEventListener("dblclick", (e) => this.onDblClick(e));
    this.root.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && e.target.classList && e.target.classList.contains("task-title")) {
        e.preventDefault();
        this.onDblClick(e);  // edit by keyboard
      }
    });
    this.root.addEventListener("submit", (e) => this.onSubmit(e));
    this.root.addEventListener("change", (e) => this.onFilterChange(e));
    this.root.addEventListener("input", (e) => {
      if (e.target.name === "due") e.target.classList.toggle("has-value", Boolean(e.target.value));
    });
    this.root.addEventListener("dragstart", (e) => this.onDragStart(e));
    this.root.addEventListener("dragover", (e) => this.onDragOver(e));
    this.root.addEventListener("dragleave", (e) => e.target.closest?.(".board-col")?.classList.remove("is-over"));
    this.root.addEventListener("drop", (e) => this.onDrop(e));
    this.root.addEventListener("dragend", () => this.root.querySelectorAll(".is-dragging, .is-over").forEach((n) => n.classList.remove("is-dragging", "is-over")));
    this.renderShell();
    this.load();
    if (options.focus === "nova") {
      options.focus = null;
      requestAnimationFrame(() => this.root.querySelector(".task-add-input")?.focus());
    }
  }

  get siteParam() {
    const site = this.options.site;
    return site === "*" ? "*" : site || "";
  }

  get sessionScoped() {
    return Boolean(this.options.terminal) && this.scope === "session";
  }

  async load() {
    // the board shows all three columns: the status filter only applies to the list
    const status = this.view === "board" ? "" : FILTERS.find((f) => f.id === this.filter).status;
    const params = new URLSearchParams({ site: this.siteParam, sort: this.sort });
    if (this.sessionScoped) params.set("terminal", this.options.terminal);
    if (status) params.set("status", status);
    if (this.tag) params.set("tag", this.tag);
    if (this.assignee) params.set("assignee", this.assignee);
    if (this.due) params.set("due", this.due);
    try {
      const [data, tags, people] = await Promise.all([get(`/api/tasks?${params}`), get("/api/tags"), get("/api/tasks/assignees")]);
      if (!this.root.isConnected) return; // the screen was switched while loading
      this.data = data;
      this.tags = tags.tags;
      this.assignees = people.assignees;
      this.renderList();
    } catch (err) {
      reportError(err);
    }
  }

  renderShell() {
    const global = this.options.site === "*";
    const siteSelect = global
      ? `<select name="site" class="select" aria-label="${t("Site da tarefa")}">
          <option value="">${t("Global")}</option>
          ${this.options.sites.map((s) => `<option value="${esc(s.name)}">${esc(s.name)}</option>`).join("")}
        </select>`
      : "";
    this.root.innerHTML = `
      <div class="tasks">
        <form class="task-add" autocomplete="off">
          <span class="task-add-icon">${icon("plus")}</span>
          <input name="title" class="task-add-input" placeholder="${t("Nova tarefa… (Enter para adicionar)")}" aria-label="${t("Título da tarefa")}" required>
          ${siteSelect}
          <label class="task-add-field">${icon("user")}<input name="assignee" class="input-bare" placeholder="${t("Responsável")}" list="assignee-options" aria-label="${t("Responsável")}" maxlength="60"></label>
          <input name="due" type="date" class="input input-date" aria-label="${t("Prazo")}" title="${t("Prazo")}" min="2000-01-01">
          <select name="priority" class="select" aria-label="${t("Prioridade")}">
            <option value="1">${PRIORITY[1]}</option><option value="2" selected>${PRIORITY[2]}</option><option value="3">${PRIORITY[3]}</option>
          </select>
          <input name="tags" class="input input-tags" placeholder="${t("tags (vírgula)")}" list="tag-options" aria-label="${t("Tags")}">
          <datalist id="tag-options"></datalist>
          <datalist id="assignee-options"></datalist>
          <button class="btn btn-primary task-add-btn" type="submit" title="${t("Adicionar (Enter)")}">${t("Adicionar")}</button>
        </form>
        <div class="task-summary" data-role="summary"></div>
        <div class="task-filters">
          ${this.options.terminal ? `<div class="segmented" role="tablist" aria-label="${t("Escopo")}">
            <button type="button" class="seg ${this.scope === "session" ? "is-on" : ""}" data-scope="session" title="${t("Só o que foi criado nesta sessão de terminal")}">${icon("terminal")}<span>${t("Esta sessão")}</span></button>
            <button type="button" class="seg ${this.scope === "site" ? "is-on" : ""}" data-scope="site">${this.options.site ? t("Todo o site") : t("Todo o Global")}</button>
          </div>` : ""}
          <div class="segmented" role="tablist" data-role="status-filter" ${this.view === "board" ? "hidden" : ""}>
            ${FILTERS.map((f) => `<button type="button" class="seg ${f.id === this.filter ? "is-on" : ""}" data-filter="${f.id}">${f.label}</button>`).join("")}
          </div>
          <select class="select select-sm" data-role="assignee" aria-label="${t("Filtrar por responsável")}"></select>
          <select class="select select-sm" data-role="due" aria-label="${t("Filtrar por prazo")}">
            ${DUE_FILTERS.map((d) => `<option value="${d.id}">${d.label}</option>`).join("")}
          </select>
          <select class="select select-sm" data-role="tag" aria-label="${t("Filtrar por tag")}"><option value="">${t("Todas as tags")}</option></select>
          <select class="select select-sm" data-role="sort" aria-label="${t("Ordenar")}">
            <option value="priority">${t("Prioridade")}</option><option value="due">${t("Prazo")}</option><option value="assignee">${t("Responsável")}</option><option value="manual">${t("Manual")}</option>
          </select>
          <div class="spacer"></div>
          <div class="segmented" role="tablist" aria-label="${t("Visão")}">
            <button type="button" class="seg ${this.view === "list" ? "is-on" : ""}" data-view="list" title="${t("Lista")}">${icon("list")}<span>${t("Lista")}</span></button>
            <button type="button" class="seg ${this.view === "board" ? "is-on" : ""}" data-view="board" title="${t("Quadro")}">${icon("columns")}<span>${t("Quadro")}</span></button>
          </div>
        </div>
        <div class="task-list" data-role="list" role="list"></div>
      </div>`;
  }

  renderSummary() {
    const s = this.data.summary;
    const p = this.data.progress;
    const box = $("[data-role=summary]", this.root);
    if (!s || !s.total) {
      box.innerHTML = "";
      return;
    }
    const quick = (id, label, value, tone, active) => `
      <button type="button" class="summary-pill ${tone} ${active ? "is-on" : ""} ${value ? "" : "is-zero"}" data-quick="${id}" aria-pressed="${active}">
        <span class="summary-num">${value}</span><span>${label}</span></button>`;
    box.innerHTML = `
      ${quick("late", s.late === 1 ? t("atrasada") : t("atrasadas"), s.late, "tone-late", this.due === "late")}
      ${quick("today", t("vencem hoje"), s.today, "tone-today", this.due === "today")}
      ${quick("unassigned", t("sem responsável"), s.unassigned, "tone-none", this.assignee === NO_ASSIGNEE)}
      <span class="summary-pill tone-open"><span class="summary-num">${s.open}</span><span>${s.open === 1 ? t("aberta") : t("abertas")}</span></span>
      <div class="spacer"></div>
      ${p && p.total ? `<div class="task-progress"><span class="num">${p.done}/${p.total}</span>${progressBar(p, "bar-wide")}<span class="num dim">${p.pct}%</span></div>` : ""}`;
  }

  renderFilters() {
    const tagSelect = $("[data-role=tag]", this.root);
    tagSelect.innerHTML = `<option value="">${t("Todas as tags")}</option>` +
      this.tags.map((tag) => `<option value="${tag.id}" ${tag.id === this.tag ? "selected" : ""}>${esc(tag.name)}</option>`).join("");
    $("#tag-options", this.root).innerHTML = this.tags.map((tag) => `<option value="${esc(tag.name)}">`).join("");
    $("#assignee-options", this.root).innerHTML = this.assignees.map((a) => `<option value="${esc(a.name)}">`).join("");
    const known = this.assignees.some((a) => a.name.toLowerCase() === this.assignee.toLowerCase());
    $("[data-role=assignee]", this.root).innerHTML = `
      <option value="">${t("Todos os responsáveis")}</option>
      <option value="${NO_ASSIGNEE}" ${this.assignee === NO_ASSIGNEE ? "selected" : ""}>${t("Sem responsável")}</option>
      ${this.assignees.map((a) => `<option value="${esc(a.name)}" ${a.name.toLowerCase() === this.assignee.toLowerCase() ? "selected" : ""}>${esc(a.name)} (${a.open})</option>`).join("")}
      ${this.assignee && this.assignee !== NO_ASSIGNEE && !known ? `<option value="${esc(this.assignee)}" selected>${esc(this.assignee)}</option>` : ""}`;
    $("[data-role=due]", this.root).value = this.due;
    $("[data-role=sort]", this.root).value = this.sort;
    $("[data-role=status-filter]", this.root).hidden = this.view === "board";
  }

  renderList() {
    this.renderSummary();
    this.renderFilters();
    const list = $("[data-role=list]", this.root);
    list.className = `task-list ${this.view === "board" ? "is-board" : ""}`;
    if (this.view === "board") {
      list.innerHTML = this.boardHtml();
    } else if (!this.data.tasks.length) {
      const filtered = this.assignee || this.due || this.tag;
      const msg = filtered ? t("Nenhuma tarefa com esses filtros.") : this.filter === "done" ? t("Nenhuma tarefa concluída ainda.") :
        this.filter === "open" ? t("Nada em aberto. Escreva uma tarefa acima e tecle Enter.") : t("Nenhuma tarefa. Escreva uma acima e tecle Enter.");
      const where = this.sessionScoped && !filtered ? ` ${t("Tarefas criadas aqui ficam na sessão “{title}”.", { title: this.options.sessionTitle })}` : "";
      list.innerHTML = `<div class="empty-inline">${icon("check-square")}<span>${esc(msg + where)}</span></div>`;
      return;
    } else {
      list.innerHTML = this.data.tasks.map((task) => this.rowHtml(task)).join("");
    }
    flashFocus(list, this.options, (id) => `[data-id="${id}"]`);
  }

  assigneeHtml(task) {
    return task.assignee
      ? `<button class="task-assignee" data-action="assignee" title="${t("Responsável: {name} · clique para trocar", { name: esc(task.assignee) })}">${avatar(task.assignee)}<span>${esc(task.assignee)}</span></button>`
      : `<button class="task-assignee is-empty" data-action="assignee" title="${t("Definir responsável")}">${icon("user")}<span>${t("Responsável")}</span></button>`;
  }

  dueHtml(task) {
    const info = dueInfo(task.due, task.status);
    return info
      ? `<button class="task-due ${info.tone}" data-action="due" title="${t("Prazo {date} · clique para mudar", { date: esc(formatDue(task.due)) })}">${icon("calendar")}<span>${esc(info.text)}</span></button>`
      : `<button class="task-due is-empty" data-action="due" title="${t("Definir prazo")}">${icon("calendar")}<span>${t("Prazo")}</span></button>`;
  }

  rowHtml(task) {
    const global = this.options.site === "*";
    const chips = task.chips.map((c) => `<span class="chip" style="--chip:${esc(c.color)}">${esc(c.name)}</span>`).join("");
    return `
      <div class="task status-${task.status}" role="listitem" data-id="${task.id}">
        <button class="task-status" data-action="cycle" aria-label="${t("Status: {status}", { status: STATUS_LABEL[task.status] })}" title="${t("{status} · clique para avançar", { status: STATUS_LABEL[task.status] })}">
          ${icon(task.status === "done" ? "circle-check" : task.status === "doing" ? "circle-half" : "circle")}
        </button>
        <span class="task-title" data-action="edit" tabindex="0" title="${t("Duplo clique ou Enter para editar")}">${esc(task.title)}</span>
        <span class="task-chips">${chips}</span>
        ${task.terminal_title && !this.sessionScoped ? `<span class="task-session" title="${t("Sessão de terminal")}">${icon("terminal")}${esc(task.terminal_title)}</span>` : ""}
        ${global ? `<span class="task-site">${esc(task.site || t("Global"))}</span>` : ""}
        ${this.assigneeHtml(task)}
        ${this.dueHtml(task)}
        <button class="task-priority p${task.priority}" data-action="priority" title="${t("Prioridade: clique para trocar")}">${PRIORITY[task.priority]}</button>
        <button class="icon-btn task-delete" data-action="delete" aria-label="${t("Excluir tarefa")}">${icon("trash")}</button>
      </div>`;
  }

  boardHtml() {
    const columns = ["todo", "doing", "done"].map((status) => {
      const tasks = this.data.tasks.filter((task) => task.status === status);
      const cards = tasks.map((task) => {
        const chips = task.chips.map((c) => `<span class="chip" style="--chip:${esc(c.color)}">${esc(c.name)}</span>`).join("");
        return `
          <article class="board-card status-${task.status} p${task.priority}" draggable="true" data-id="${task.id}">
            <div class="board-card-top">
              <span class="board-priority p${task.priority}" title="${t("Prioridade {priority}", { priority: PRIORITY[task.priority] })}"></span>
              <span class="task-title board-title" title="${t("Duplo clique para editar")}">${esc(task.title)}</span>
              <button class="icon-btn icon-btn-sm task-delete" data-action="delete" aria-label="${t("Excluir tarefa")}">${icon("trash")}</button>
            </div>
            ${chips ? `<div class="board-chips">${chips}</div>` : ""}
            <div class="board-meta">${this.assigneeHtml(task)}${this.dueHtml(task)}</div>
          </article>`;
      }).join("");
      return `
        <section class="board-col" data-status="${status}" aria-label="${STATUS_LABEL[status]}">
          <header class="board-col-head"><span class="board-dot status-${status}"></span><h3>${STATUS_LABEL[status]}</h3><span class="count">${tasks.length}</span></header>
          <div class="board-cards">${cards || `<div class="board-empty">${t("Arraste tarefas para cá")}</div>`}</div>
        </section>`;
    }).join("");
    return `<div class="board">${columns}</div>`;
  }

  async onSubmit(event) {
    event.preventDefault();
    const form = event.target;
    if (!form.classList.contains("task-add")) return;
    const data = new FormData(form);
    const title = String(data.get("title") || "").trim();
    if (!title) return;
    const tags = String(data.get("tags") || "").split(",").map((s) => s.trim()).filter(Boolean);
    const site = this.options.site === "*" ? String(data.get("site") || "") : this.siteParam;
    try {
      await post("/api/tasks", {
        site, title, priority: Number(data.get("priority")), due: data.get("due") || null, tags,
        assignee: String(data.get("assignee") || "").trim() || null,
        terminal: this.sessionScoped ? this.options.terminal : null,
      });
      form.title.value = "";
      form.due.value = "";
      form.due.classList.remove("has-value");
      form.tags.value = "";
      form.title.focus(); // assignee stays filled in to log several tasks for the same person
      await this.load();
      this.options.onChange();
    } catch (err) {
      reportError(err);
    }
  }

  onFilterChange(event) {
    const role = event.target.dataset.role;
    if (role === "tag") this.tag = event.target.value;
    else if (role === "sort") this.sort = event.target.value;
    else if (role === "assignee") this.assignee = event.target.value;
    else if (role === "due") this.due = event.target.value;
    else return;
    this.load();
  }

  async onClick(event) {
    const scope = event.target.closest("[data-scope]");
    if (scope) {
      this.scope = scope.dataset.scope;
      this.root.querySelectorAll("[data-scope]").forEach((b) => b.classList.toggle("is-on", b === scope));
      this.load();
      return;
    }
    const view = event.target.closest("[data-view]");
    if (view) {
      this.view = view.dataset.view;
      try { localStorage.setItem(VIEW_KEY, this.view); } catch { /* this window only */ }
      this.root.querySelectorAll("[data-view]").forEach((b) => b.classList.toggle("is-on", b === view));
      this.load();
      return;
    }
    const quick = event.target.closest("[data-quick]");
    if (quick) {
      const id = quick.dataset.quick;
      if (id === "unassigned") this.assignee = this.assignee === NO_ASSIGNEE ? "" : NO_ASSIGNEE;
      else this.due = this.due === id ? "" : id;
      if (this.view === "list" && this.filter === "done") this.filter = "open";
      this.load();
      return;
    }
    const seg = event.target.closest("[data-filter]");
    if (seg) {
      this.filter = seg.dataset.filter;
      this.root.querySelectorAll("[data-filter]").forEach((b) => b.classList.toggle("is-on", b === seg));
      this.load();
      return;
    }
    const target = event.target.closest("[data-action]");
    const row = event.target.closest("[data-id]");
    if (!target || !row) return;
    const id = row.dataset.id;
    const task = this.data.tasks.find((t) => t.id === id);
    const action = target.dataset.action;
    try {
      if (action === "assignee") return this.editAssignee(target, task);
      if (action === "due") return this.editDue(target, task);
      if (action === "cycle") {
        await post(`/api/tasks/${id}/cycle`);
      } else if (action === "priority") {
        await patch(`/api/tasks/${id}`, { priority: (task.priority % 3) + 1 });
      } else if (action === "delete") {
        await del(`/api/tasks/${id}`);
        toast(t("Tarefa excluída: {title}", { title: task.title }), {
          action: { label: t("Desfazer"), run: () => post("/api/tasks/undo").then(() => { this.load(); this.options.onChange(); }).catch(reportError) },
          timeout: 5000,
        });
      } else {
        return null;
      }
      await this.load();
      this.options.onChange();
    } catch (err) {
      reportError(err);
    }
    return null;
  }

  /** Swaps the button for an in-place field; Enter or blur saves, Esc cancels. */
  inlineEditor(button, input, save) {
    button.replaceWith(input);
    input.focus();
    if (input.select) input.select();
    let done = false;
    const finish = async (commit) => {
      if (done) return;
      done = true;
      if (commit) {
        try {
          await save(input.value);
          this.options.onChange();
        } catch (err) {
          reportError(err);
        }
      }
      this.load();
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); finish(true); }
      if (e.key === "Escape") finish(false);
    });
    input.addEventListener("blur", () => finish(true));
    input.addEventListener("click", (e) => e.stopPropagation());
    return finish;
  }

  editAssignee(button, task) {
    const input = document.createElement("input");
    input.className = "input inline-edit inline-assignee";
    input.value = task.assignee || "";
    input.placeholder = t("Responsável");
    input.maxLength = 60;
    input.setAttribute("list", "assignee-options");
    input.setAttribute("aria-label", t("Responsável"));
    this.inlineEditor(button, input, (value) => {
      const next = value.trim();
      return next === (task.assignee || "") ? null : patch(`/api/tasks/${task.id}`, { assignee: next || null });
    });
    return null;
  }

  editDue(button, task) {
    const input = document.createElement("input");
    input.type = "date";
    input.className = "input inline-edit inline-due";
    input.value = task.due || "";
    input.setAttribute("aria-label", t("Prazo"));
    const finish = this.inlineEditor(button, input, (value) =>
      (value || null) === (task.due || null) ? null : patch(`/api/tasks/${task.id}`, { due: value || null }));
    input.addEventListener("change", () => finish(true));
    return null;
  }

  onDragStart(event) {
    const card = event.target.closest?.(".board-card");
    if (!card) return;
    this.dragging = card.dataset.id;
    card.classList.add("is-dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", card.dataset.id);
  }

  onDragOver(event) {
    const col = event.target.closest?.(".board-col");
    if (!col || !this.dragging) return;
    event.preventDefault();
    this.root.querySelectorAll(".board-col.is-over").forEach((c) => c !== col && c.classList.remove("is-over"));
    col.classList.add("is-over");
  }

  async onDrop(event) {
    const col = event.target.closest?.(".board-col");
    if (!col || !this.dragging) return;
    event.preventDefault();
    const id = this.dragging;
    this.dragging = null;
    const task = this.data.tasks.find((t) => t.id === id);
    if (!task || task.status === col.dataset.status) {
      this.load();
      return;
    }
    try {
      await patch(`/api/tasks/${id}`, { status: col.dataset.status });
      await this.load();
      this.options.onChange();
    } catch (err) {
      reportError(err);
    }
  }

  onDblClick(event) {
    const title = event.target.closest(".task-title");
    if (!title) return;
    const row = title.closest("[data-id]");
    const task = this.data.tasks.find((t) => t.id === row.dataset.id);
    const input = document.createElement("input");
    input.className = "input task-edit";
    input.value = task.title;
    title.replaceWith(input);
    input.focus();
    input.select();
    let done = false;
    const finish = async (save) => {
      if (done) return;
      done = true;
      if (save && input.value.trim() && input.value.trim() !== task.title) {
        try {
          await patch(`/api/tasks/${task.id}`, { title: input.value.trim() });
        } catch (err) {
          reportError(err);
        }
      }
      this.load();
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") finish(true);
      if (e.key === "Escape") finish(false);
    });
    input.addEventListener("blur", () => finish(true));
  }

  destroy() {}
}
