// Tarefas como mini gerenciador: responsável, prazo, resumo, filtros e visões Lista ou Quadro (arrastar muda o status).

import { del, get, patch, post } from "../api.mjs";
import { $, flashFocus, esc, formatDue, icon, progressBar, reportError, toast, todayISO } from "../dom.mjs";

const PRIORITY = { 1: "Alta", 2: "Média", 3: "Baixa" };
const STATUS_LABEL = { todo: "A fazer", doing: "Fazendo", done: "Feito" };
const FILTERS = [
  { id: "open", label: "Abertas", status: "todo,doing" },
  { id: "all", label: "Todas", status: "" },
  { id: "done", label: "Concluídas", status: "done" },
];
const DUE_FILTERS = [
  { id: "", label: "Qualquer prazo" },
  { id: "late", label: "Atrasadas" },
  { id: "today", label: "Vencem hoje" },
  { id: "week", label: "Próximos 7 dias" },
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

/** Prazo em linguagem de gestão: Hoje, Amanhã, Atrasada 3 d, dia da semana na próxima semana. */
function dueInfo(due, status) {
  if (!due) return null;
  const today = new Date(`${todayISO()}T00:00:00`);
  const date = new Date(`${due}T00:00:00`);
  const days = Math.round((date - today) / 86400000);
  if (status !== "done" && days < 0) return { text: `Atrasada ${-days} d`, tone: "is-late" };
  if (days === 0) return { text: "Hoje", tone: status === "done" ? "" : "is-today" };
  if (days === 1) return { text: "Amanhã", tone: status === "done" ? "" : "is-soon" };
  if (days > 1 && days <= 6) {
    const weekday = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"][date.getDay()];
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
    // "nova": veio do menu da sessão, cursor no campo de tarefa nova; outro id: item aberto pela árvore (pode estar concluído)
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
        this.onDblClick(e);  // editar pelo teclado
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
    // o quadro mostra as três colunas: o filtro de status só vale na lista
    const status = this.view === "board" ? "" : FILTERS.find((f) => f.id === this.filter).status;
    const params = new URLSearchParams({ site: this.siteParam, sort: this.sort });
    if (this.sessionScoped) params.set("terminal", this.options.terminal);
    if (status) params.set("status", status);
    if (this.tag) params.set("tag", this.tag);
    if (this.assignee) params.set("assignee", this.assignee);
    if (this.due) params.set("due", this.due);
    try {
      const [data, tags, people] = await Promise.all([get(`/api/tasks?${params}`), get("/api/tags"), get("/api/tasks/assignees")]);
      if (!this.root.isConnected) return; // a tela foi trocada enquanto carregava
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
      ? `<select name="site" class="select" aria-label="Site da tarefa">
          <option value="">Global</option>
          ${this.options.sites.map((s) => `<option value="${esc(s.name)}">${esc(s.name)}</option>`).join("")}
        </select>`
      : "";
    this.root.innerHTML = `
      <div class="tasks">
        <form class="task-add" autocomplete="off">
          <span class="task-add-icon">${icon("plus")}</span>
          <input name="title" class="task-add-input" placeholder="Nova tarefa… (Enter para adicionar)" aria-label="Título da tarefa" required>
          ${siteSelect}
          <label class="task-add-field">${icon("user")}<input name="assignee" class="input-bare" placeholder="Responsável" list="assignee-options" aria-label="Responsável" maxlength="60"></label>
          <input name="due" type="date" class="input input-date" aria-label="Prazo" title="Prazo" min="2000-01-01">
          <select name="priority" class="select" aria-label="Prioridade">
            <option value="1">Alta</option><option value="2" selected>Média</option><option value="3">Baixa</option>
          </select>
          <input name="tags" class="input input-tags" placeholder="tags (vírgula)" list="tag-options" aria-label="Tags">
          <datalist id="tag-options"></datalist>
          <datalist id="assignee-options"></datalist>
          <button class="btn btn-primary task-add-btn" type="submit" title="Adicionar (Enter)">Adicionar</button>
        </form>
        <div class="task-summary" data-role="summary"></div>
        <div class="task-filters">
          ${this.options.terminal ? `<div class="segmented" role="tablist" aria-label="Escopo">
            <button type="button" class="seg ${this.scope === "session" ? "is-on" : ""}" data-scope="session" title="Só o que foi criado nesta sessão de terminal">${icon("terminal")}<span>Esta sessão</span></button>
            <button type="button" class="seg ${this.scope === "site" ? "is-on" : ""}" data-scope="site">Todo o ${this.options.site ? "site" : "Global"}</button>
          </div>` : ""}
          <div class="segmented" role="tablist" data-role="status-filter" ${this.view === "board" ? "hidden" : ""}>
            ${FILTERS.map((f) => `<button type="button" class="seg ${f.id === this.filter ? "is-on" : ""}" data-filter="${f.id}">${f.label}</button>`).join("")}
          </div>
          <select class="select select-sm" data-role="assignee" aria-label="Filtrar por responsável"></select>
          <select class="select select-sm" data-role="due" aria-label="Filtrar por prazo">
            ${DUE_FILTERS.map((d) => `<option value="${d.id}">${d.label}</option>`).join("")}
          </select>
          <select class="select select-sm" data-role="tag" aria-label="Filtrar por tag"><option value="">Todas as tags</option></select>
          <select class="select select-sm" data-role="sort" aria-label="Ordenar">
            <option value="priority">Prioridade</option><option value="due">Prazo</option><option value="assignee">Responsável</option><option value="manual">Manual</option>
          </select>
          <div class="spacer"></div>
          <div class="segmented" role="tablist" aria-label="Visão">
            <button type="button" class="seg ${this.view === "list" ? "is-on" : ""}" data-view="list" title="Lista">${icon("list")}<span>Lista</span></button>
            <button type="button" class="seg ${this.view === "board" ? "is-on" : ""}" data-view="board" title="Quadro">${icon("columns")}<span>Quadro</span></button>
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
      ${quick("late", s.late === 1 ? "atrasada" : "atrasadas", s.late, "tone-late", this.due === "late")}
      ${quick("today", "vencem hoje", s.today, "tone-today", this.due === "today")}
      ${quick("unassigned", "sem responsável", s.unassigned, "tone-none", this.assignee === NO_ASSIGNEE)}
      <span class="summary-pill tone-open"><span class="summary-num">${s.open}</span><span>${s.open === 1 ? "aberta" : "abertas"}</span></span>
      <div class="spacer"></div>
      ${p && p.total ? `<div class="task-progress"><span class="num">${p.done}/${p.total}</span>${progressBar(p, "bar-wide")}<span class="num dim">${p.pct}%</span></div>` : ""}`;
  }

  renderFilters() {
    const tagSelect = $("[data-role=tag]", this.root);
    tagSelect.innerHTML = `<option value="">Todas as tags</option>` +
      this.tags.map((t) => `<option value="${t.id}" ${t.id === this.tag ? "selected" : ""}>${esc(t.name)}</option>`).join("");
    $("#tag-options", this.root).innerHTML = this.tags.map((t) => `<option value="${esc(t.name)}">`).join("");
    $("#assignee-options", this.root).innerHTML = this.assignees.map((a) => `<option value="${esc(a.name)}">`).join("");
    const known = this.assignees.some((a) => a.name.toLowerCase() === this.assignee.toLowerCase());
    $("[data-role=assignee]", this.root).innerHTML = `
      <option value="">Todos os responsáveis</option>
      <option value="${NO_ASSIGNEE}" ${this.assignee === NO_ASSIGNEE ? "selected" : ""}>Sem responsável</option>
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
      const msg = filtered ? "Nenhuma tarefa com esses filtros." : this.filter === "done" ? "Nenhuma tarefa concluída ainda." :
        this.filter === "open" ? "Nada em aberto. Escreva uma tarefa acima e tecle Enter." : "Nenhuma tarefa. Escreva uma acima e tecle Enter.";
      const where = this.sessionScoped && !filtered ? ` Tarefas criadas aqui ficam na sessão “${this.options.sessionTitle}”.` : "";
      list.innerHTML = `<div class="empty-inline">${icon("check-square")}<span>${esc(msg + where)}</span></div>`;
      return;
    } else {
      list.innerHTML = this.data.tasks.map((t) => this.rowHtml(t)).join("");
    }
    flashFocus(list, this.options, (id) => `[data-id="${id}"]`);
  }

  assigneeHtml(t) {
    return t.assignee
      ? `<button class="task-assignee" data-action="assignee" title="Responsável: ${esc(t.assignee)} · clique para trocar">${avatar(t.assignee)}<span>${esc(t.assignee)}</span></button>`
      : `<button class="task-assignee is-empty" data-action="assignee" title="Definir responsável">${icon("user")}<span>Responsável</span></button>`;
  }

  dueHtml(t) {
    const info = dueInfo(t.due, t.status);
    return info
      ? `<button class="task-due ${info.tone}" data-action="due" title="Prazo ${esc(formatDue(t.due))} · clique para mudar">${icon("calendar")}<span>${esc(info.text)}</span></button>`
      : `<button class="task-due is-empty" data-action="due" title="Definir prazo">${icon("calendar")}<span>Prazo</span></button>`;
  }

  rowHtml(t) {
    const global = this.options.site === "*";
    const chips = t.chips.map((c) => `<span class="chip" style="--chip:${esc(c.color)}">${esc(c.name)}</span>`).join("");
    return `
      <div class="task status-${t.status}" role="listitem" data-id="${t.id}">
        <button class="task-status" data-action="cycle" aria-label="Status: ${STATUS_LABEL[t.status]}" title="${STATUS_LABEL[t.status]} · clique para avançar">
          ${icon(t.status === "done" ? "circle-check" : t.status === "doing" ? "circle-half" : "circle")}
        </button>
        <span class="task-title" data-action="edit" tabindex="0" title="Duplo clique ou Enter para editar">${esc(t.title)}</span>
        <span class="task-chips">${chips}</span>
        ${t.terminal_title && !this.sessionScoped ? `<span class="task-session" title="Sessão de terminal">${icon("terminal")}${esc(t.terminal_title)}</span>` : ""}
        ${global ? `<span class="task-site">${esc(t.site || "Global")}</span>` : ""}
        ${this.assigneeHtml(t)}
        ${this.dueHtml(t)}
        <button class="task-priority p${t.priority}" data-action="priority" title="Prioridade: clique para trocar">${PRIORITY[t.priority]}</button>
        <button class="icon-btn task-delete" data-action="delete" aria-label="Excluir tarefa">${icon("trash")}</button>
      </div>`;
  }

  boardHtml() {
    const columns = ["todo", "doing", "done"].map((status) => {
      const tasks = this.data.tasks.filter((t) => t.status === status);
      const cards = tasks.map((t) => {
        const chips = t.chips.map((c) => `<span class="chip" style="--chip:${esc(c.color)}">${esc(c.name)}</span>`).join("");
        return `
          <article class="board-card status-${t.status} p${t.priority}" draggable="true" data-id="${t.id}">
            <div class="board-card-top">
              <span class="board-priority p${t.priority}" title="Prioridade ${PRIORITY[t.priority]}"></span>
              <span class="task-title board-title" title="Duplo clique para editar">${esc(t.title)}</span>
              <button class="icon-btn icon-btn-sm task-delete" data-action="delete" aria-label="Excluir tarefa">${icon("trash")}</button>
            </div>
            ${chips ? `<div class="board-chips">${chips}</div>` : ""}
            <div class="board-meta">${this.assigneeHtml(t)}${this.dueHtml(t)}</div>
          </article>`;
      }).join("");
      return `
        <section class="board-col" data-status="${status}" aria-label="${STATUS_LABEL[status]}">
          <header class="board-col-head"><span class="board-dot status-${status}"></span><h3>${STATUS_LABEL[status]}</h3><span class="count">${tasks.length}</span></header>
          <div class="board-cards">${cards || `<div class="board-empty">Arraste tarefas para cá</div>`}</div>
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
      form.title.focus(); // responsável fica preenchido para lançar várias tarefas da mesma pessoa
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
      try { localStorage.setItem(VIEW_KEY, this.view); } catch { /* só nesta janela */ }
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
        toast(`Tarefa excluída: ${task.title}`, {
          action: { label: "Desfazer", run: () => post("/api/tasks/undo").then(() => { this.load(); this.options.onChange(); }).catch(reportError) },
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

  /** Troca o botão por um campo no lugar; Enter ou sair salva, Esc cancela. */
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
    input.placeholder = "Responsável";
    input.maxLength = 60;
    input.setAttribute("list", "assignee-options");
    input.setAttribute("aria-label", "Responsável");
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
    input.setAttribute("aria-label", "Prazo");
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
