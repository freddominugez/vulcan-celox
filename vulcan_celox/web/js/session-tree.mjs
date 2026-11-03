// Árvore de sessões da barra lateral: abertas e encerradas, cada uma com tarefas, post-its e tags.
// Clicar num nó abre a sessão (ou o item) na área da direita.

import { confirmDialog } from "./ai.mjs";
import { del, get, patch, post } from "./api.mjs";
import { esc, icon, reportError, toast } from "./dom.mjs";
import { syncPorts } from "./terminal-ports.mjs";
import { terminals } from "./terminals.mjs";
import { agentMark } from "./agents-ui.mjs";
import { t } from "./i18n.mjs";

const STORAGE_KEY = "vulcan-tree-open";
const DEFAULT_OPEN = ["section:sessions", "section:sites", "group:open", "group:closed"];
const PAGE = 30;
const WEEKDAYS = [t("dom"), t("seg"), t("ter"), t("qua"), t("qui"), t("sex"), t("sáb")];

function dayKey(iso) {
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function dayLabel(key) {
  const today = dayKey(new Date().toISOString());
  const yesterday = dayKey(new Date(Date.now() - 86400000).toISOString());
  if (key === today) return t("Hoje");
  if (key === yesterday) return t("Ontem");
  const [y, m, d] = key.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  return `${WEEKDAYS[date.getDay()]}, ${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}${y !== new Date().getFullYear() ? `/${y}` : ""}`;
}

function loadExpanded() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return new Set(raw ? JSON.parse(raw) : DEFAULT_OPEN);
  } catch {
    return new Set(DEFAULT_OPEN);
  }
}

/** Rota da sessão na área da direita; `focus` destaca um item dentro da aba. */
export function sessionHash(session, tab = "terminal", focus = "") {
  const tail = `${tab}/${session.id}${focus ? `/${encodeURIComponent(focus)}` : ""}`;
  return session.site ? `#/sites/${encodeURIComponent(session.site)}/${tail}` : `#/terminals/${tail}`;
}

export class SessionTree {
  /** @param {{navigate: Function, route: Function}} options */
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.expanded = loadExpanded();
    this.data = null;
    this.signature = "";
    this.closedLimit = PAGE;
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.root.addEventListener("contextmenu", (e) => {
      const node = e.target.closest(".tree-node");
      if (!node) return;
      e.preventDefault();
      this.openMenu(node.dataset.id, e.clientX, e.clientY);
    });
    this.onDocDown = (e) => {
      if (this.menu && !this.menu.contains(e.target)) this.closeMenu();
    };
    document.addEventListener("mousedown", this.onDocDown);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") this.closeMenu();
    });
  }

  isOpen(key) {
    return this.expanded.has(key);
  }

  toggle(key) {
    if (this.expanded.has(key)) this.expanded.delete(key);
    else this.expanded.add(key);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify([...this.expanded]));
    } catch {
      /* armazenamento indisponível: vale só nesta janela */
    }
  }

  async load() {
    try {
      this.data = await get(`/api/sessions/tree?closed=${this.closedLimit}`);
      this.render();
      syncPorts();
    } catch {
      /* servidor fora do ar: a barra lateral mostra o estado offline pelo app */
    }
  }

  render(force = false) {
    if (!this.data) return;
    const route = this.options.route();
    const active = route.session || "";
    const signature = JSON.stringify([this.data, [...this.expanded], active]);
    if (!force && signature === this.signature) return;
    this.signature = signature;
    const { open, closed, closed_total: closedTotal } = this.data;
    const sectionOpen = this.isOpen("section:sessions");
    this.root.innerHTML = `
      <button class="side-heading side-toggle" data-toggle="section:sessions" aria-expanded="${sectionOpen}">
        ${icon("chevron-right", "side-chevron")}<span>${t("Sessões")}</span><span class="side-heading-count">${open.length + closedTotal || ""}</span>
      </button>
      ${sectionOpen ? `<div class="tree" role="tree" aria-label="${t("Sessões de terminal")}">
        ${this.groupHtml("open", t("Abertas"), open, open.length, active)}
        ${this.historyHtml(closed, closedTotal, active)}
      </div>` : ""}`;
  }

  groupHtml(key, label, sessions, total, active) {
    const groupKey = `group:${key}`;
    const expanded = this.isOpen(groupKey);
    const body = sessions.length
      ? sessions.map((s) => this.sessionHtml(s, active)).join("")
      : `<div class="tree-empty">${t("Nenhum terminal aberto.")}</div>`;
    return `
      <div class="tree-group" role="group">
        <button class="tree-group-head" data-toggle="${groupKey}" aria-expanded="${expanded}">
          ${icon("chevron-right", "side-chevron")}<span>${label}</span><span class="tree-count">${total || ""}</span>
        </button>
        ${expanded ? `<div class="tree-group-body">${body}</div>` : ""}
      </div>`;
  }

  /** Pasta Histórico: sessões encerradas em subpastas por dia (a mais recente aberta por padrão). */
  historyHtml(closed, total, active) {
    const expanded = this.isOpen("group:closed");
    const days = new Map();
    for (const s of closed) {
      const key = dayKey(s.closed_at || s.created_at);
      if (!days.has(key)) days.set(key, []);
      days.get(key).push(s);
    }
    const folders = [...days.entries()].map(([key, sessions], index) => {
      const open = index === 0 ? !this.isOpen(`dayx:${key}`) : this.isOpen(`day:${key}`);
      const toggle = index === 0 ? `dayx:${key}` : `day:${key}`;
      return `
        <div class="tree-day" role="group">
          <button class="tree-day-head" data-toggle="${toggle}" aria-expanded="${open}">
            ${icon("chevron-right", "side-chevron")}${icon("folder")}<span>${esc(dayLabel(key))}</span><span class="tree-count">${sessions.length}</span>
          </button>
          ${open ? `<div class="tree-day-body">${sessions.map((s) => this.sessionHtml(s, active)).join("")}</div>` : ""}
        </div>`;
    }).join("");
    const body = closed.length
      ? folders + (total > closed.length ? `<button class="tree-more" data-action="more">${t("Carregar mais ({n})", { n: total - closed.length })}</button>` : "")
      : `<div class="tree-empty">${t("Ao fechar um terminal ele aparece aqui, com a memória do que foi feito.")}</div>`;
    return `
      <div class="tree-group tree-history" role="group">
        <button class="tree-group-head" data-toggle="group:closed" aria-expanded="${expanded}">
          ${icon("chevron-right", "side-chevron")}${icon("folder")}<span>${t("Histórico")}</span><span class="tree-count">${total || ""}</span>
        </button>
        ${expanded ? `<div class="tree-group-body">${body}</div>` : ""}
      </div>`;
  }

  sessionHtml(s, active) {
    const key = `s:${s.id}`;
    const expanded = this.isOpen(key);
    const items = s.task_list.length + s.note_list.length + s.tags.length;
    const progress = s.tasks.total ? `<span class="tree-meta">${s.tasks.done}/${s.tasks.total}</span>` : "";
    const where = s.site || "Global";
    return `
      <div class="tree-node ${s.id === active ? "is-on" : ""} ${s.open ? "is-open" : "is-closed"} ${s.theme ? `has-theme t-${esc(s.theme)}` : ""}" data-id="${s.id}" role="treeitem" aria-expanded="${expanded}">
        <div class="tree-row">
          <button class="tree-twisty" data-toggle="${key}" aria-expanded="${expanded && items > 0}" aria-label="${expanded ? t("Recolher {title}", { title: esc(s.title) }) : t("Expandir {title}", { title: esc(s.title) })}" ${items ? "" : "disabled"}>
            ${items ? icon("chevron-right", "side-chevron") : ""}</button>
          <a class="tree-link" href="${sessionHash(s)}" title="${esc(`${s.title} · ${where}${s.has_doc ? ` · ${t("documentada")}` : ""}`)}">
            ${icon(s.open ? "terminal" : "clock")}
            <span class="tree-title">${esc(s.title)}</span>
            <span class="tree-site">${esc(where)}</span>
            ${(s.agents || []).length ? `<span class="tree-agents" title="${t("Sessões de agente pareadas")}">${[...new Set(s.agents.map((a) => a.agent))].map(agentMark).join("")}</span>` : ""}
            ${s.has_doc ? `<span class="tree-doc" title="${t("Tem documentação")}">${icon("book")}</span>` : ""}
            ${progress}
          </a>
          <button class="tree-menu-btn" data-menu="${s.id}" aria-label="${t("Opções da sessão {title}", { title: esc(s.title) })}" title="${t("Opções")}">${icon("dots")}</button>
        </div>
        ${expanded && items ? `<div class="tree-children">
          ${s.task_list.map((t) => `<a class="tree-leaf status-${t.status}" href="${sessionHash(s, "tasks", t.id)}">
              ${icon(t.status === "done" ? "circle-check" : t.status === "doing" ? "circle-half" : "circle")}<span>${esc(t.title)}</span></a>`).join("")}
          ${s.note_list.map((n) => `<a class="tree-leaf" href="${sessionHash(s, "notes", n.id)}">
              <span class="tree-swatch swatch-${esc(n.color)}"></span><span>${esc(n.title || t("Post-it sem texto"))}</span></a>`).join("")}
          ${s.tags.length ? `<div class="tree-tags">${s.tags.map((t) => `<a class="chip" style="--chip:${esc(t.color)}" href="${sessionHash(s, "tags", t.id)}">${esc(t.name)}</a>`).join("")}</div>` : ""}
        </div>` : ""}
      </div>`;
  }

  // ── opções da sessão ─────────────────────────────────────────────────
  findSession(id) {
    return this.data ? [...this.data.open, ...this.data.closed].find((s) => s.id === id) : null;
  }

  openMenu(id, x, y) {
    const s = this.findSession(id);
    if (!s) return;
    this.closeMenu();
    const menu = document.createElement("div");
    menu.className = "tree-menu";
    menu.setAttribute("role", "menu");
    menu.innerHTML = `
      <div class="tree-menu-head">${esc(s.title)}</div>
      <button role="menuitem" data-op="rename">${icon("edit")}<span>${t("Renomear")}</span></button>
      <button role="menuitem" data-op="note">${icon("note")}<span>${t("Adicionar post-it")}</span></button>
      <button role="menuitem" data-op="task">${icon("check-square")}<span>${t("Adicionar tarefa")}</span></button>
      <div class="tree-menu-sep"></div>
      <button role="menuitem" data-op="delete" class="is-danger" ${s.open ? `disabled title="${t("Feche o terminal antes de apagar")}"` : ""}>${icon("trash")}<span>${t("Apagar sessão…")}</span></button>`;
    document.body.appendChild(menu);
    const rect = menu.getBoundingClientRect();
    menu.style.left = `${Math.min(x, window.innerWidth - rect.width - 8)}px`;
    menu.style.top = `${Math.min(y, window.innerHeight - rect.height - 8)}px`;
    menu.addEventListener("click", (e) => {
      const item = e.target.closest("[data-op]");
      if (!item || item.disabled) return;
      this.closeMenu();
      this.runOp(item.dataset.op, s);
    });
    this.menu = menu;
    menu.querySelector("button:not([disabled])").focus();
  }

  closeMenu() {
    if (this.menu) this.menu.remove();
    this.menu = null;
  }

  async runOp(op, s) {
    try {
      if (op === "rename") return this.rename(s);
      if (op === "note") {
        const note = await post("/api/notes", { terminal: s.id, text: "" });
        this.options.navigate(sessionHash(s, "notes", note.id));
      }
      if (op === "task") this.options.navigate(sessionHash(s, "tasks", "nova"));
      if (op === "delete") await this.remove(s);
      await this.load();
    } catch (err) {
      reportError(err);
    }
    return null;
  }

  rename(s) {
    const node = this.root.querySelector(`.tree-node[data-id="${s.id}"]`);
    const label = node && node.querySelector(".tree-title");
    if (!label) return;
    const input = document.createElement("input");
    input.className = "tree-rename";
    input.value = s.title;
    input.maxLength = 60;
    label.replaceWith(input);
    input.focus();
    input.select();
    let done = false;
    const finish = async (save) => {
      if (done) return;
      done = true;
      const title = input.value.trim();
      if (save && title && title !== s.title) {
        try {
          if (terminals.get(s.id)) await terminals.rename(s.id, title);
          else await patch(`/api/sessions/${s.id}`, { title });
          toast(t("Sessão renomeada para “{title}”.", { title }), { kind: "ok" });
          window.dispatchEvent(new CustomEvent("vulcan-sessions-changed"));
        } catch (err) {
          reportError(err);
        }
      }
      this.signature = "";
      await this.load();
    };
    input.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Enter") finish(true);
      if (e.key === "Escape") finish(false);
    });
    input.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); });
    input.addEventListener("blur", () => finish(true));
  }

  async remove(s) {
    const items = s.task_list.length + s.note_list.length;
    let deleteItems = false;
    const ok = await confirmDialog({
      title: t("Apagar a sessão “{title}”?", { title: s.title }),
      confirmLabel: t("Apagar sessão"),
      danger: true,
      body: `<p>${t("A sessão sai do Histórico e do índice.")} ${s.has_doc ? t("A memória e a documentação vão para a Lixeira, de onde podem ser recuperadas.") : t("A memória vai para a Lixeira, de onde pode ser recuperada.")}</p>
        ${items ? `<label class="dialog-check"><input type="checkbox" data-delete-items>
          <span>${t("Apagar também {tasks} e {notes} desta sessão", { tasks: s.task_list.length === 1 ? t("1 tarefa") : t("{n} tarefas", { n: s.task_list.length }), notes: s.note_list.length === 1 ? t("1 post-it") : t("{n} post-its", { n: s.note_list.length }) })}</span></label>
          <p class="dim">${t("Sem marcar, eles continuam no {where}, sem sessão.", { where: esc(s.site || "Global") })}</p>` : ""}`,
      onDecide: (answer, root) => {
        const box = root.querySelector("[data-delete-items]");
        deleteItems = Boolean(answer && box && box.checked);
      },
    });
    if (!ok) return;
    await del(`/api/sessions/${s.id}?items=${deleteItems ? "delete" : "keep"}`);
    toast(t("Sessão “{title}” apagada. Arquivos na Lixeira.", { title: s.title }), { kind: "ok" });
    window.dispatchEvent(new CustomEvent("vulcan-sessions-changed"));
    if (this.options.route().session === s.id) {
      this.options.navigate(s.site ? `#/sites/${encodeURIComponent(s.site)}/terminal` : "#/terminals/terminal");
    }
  }

  onClick(event) {
    const menuBtn = event.target.closest("[data-menu]");
    if (menuBtn) {
      event.preventDefault();
      const rect = menuBtn.getBoundingClientRect();
      this.openMenu(menuBtn.dataset.menu, rect.left, rect.bottom + 4);
      return;
    }
    if (event.target.closest("[data-action='more']")) {
      this.closedLimit += PAGE;
      this.load();
      return;
    }
    const toggle = event.target.closest("[data-toggle]");
    if (toggle && this.root.contains(toggle)) {
      event.preventDefault();
      this.toggle(toggle.dataset.toggle);
      this.render(true);
      return;
    }
    const link = event.target.closest("a.tree-link");
    if (link) {
      // abrir uma sessão também mostra os itens dela
      const id = link.closest(".tree-node").querySelector("[data-toggle^='s:']").dataset.toggle;
      if (!this.isOpen(id)) this.toggle(id);
    }
  }
}
