// Sidebar session tree: open and closed, each with tasks, sticky notes and tags.
// Clicking a node opens the session (or the item) in the right-hand area.

import { confirmDialog } from "./ai.mjs";
import { labelFor } from "./attention-state.mjs";
import { isHidden } from "./sidebar-prefs.mjs";
import { isRail } from "./sidebar-rail.mjs";
import { del, get, patch, post } from "./api.mjs";
import { esc, icon, reportError, shortPath, toast } from "./dom.mjs";
import { syncPorts } from "./terminal-ports.mjs";
import { sessionHash, terminals } from "./terminal-pool.mjs";
import { editTerminalIdentity } from "./terminal-identity.mjs";
import { openNote } from "./note-dialog.mjs";
import { agentMark } from "./agents-ui.mjs";
import { t } from "./i18n.mjs";

const STORAGE_KEY = "vulcan-tree-open";
const DEFAULT_OPEN = ["section:sites", "group:open"];
const MAX_CLOSED = 200;
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
    const saved = raw && JSON.parse(raw);
    return new Set(Array.isArray(saved) && saved.every((value) => typeof value === "string") ? saved : DEFAULT_OPEN);
  } catch {
    return new Set(DEFAULT_OPEN);
  }
}

export class SessionTree {
  /** @param {{navigate: Function, route: Function}} options */
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.expanded = loadExpanded();
    this.data = null;
    window.addEventListener("vulcan-note-changed", () => this.load());
    window.addEventListener("vulcan-sessions-changed", () => this.load());
    this.head = root.querySelector("#side-terminal-head");
    this.body = root.querySelector("#side-sessions");
    this.generation = 0;
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
      /* storage unavailable: only applies to this window */
    }
  }

  async load() {
    const generation = ++this.generation;
    try {
      const data = await get(`/api/sessions/tree?closed=${this.closedLimit}`);
      if (generation !== this.generation) return;
      this.data = data;
      this.render();
      syncPorts();
    } catch {
      /* server down: the sidebar shows the offline state through the app */
    }
  }

  render(force = false) {
    const route = this.options.route();
    const active = route.session || "";
    const section = !isHidden("section-sessions");
    const link = !isHidden("terminals");
    const rail = isRail();
    const expanded = this.isOpen("group:open");
    const live = terminals.live();
    const headLink = link ? `<a class="nav-item ${route.name === "terminals" ? "is-on" : ""}" href="#/terminals"
      title="${t("Terminais")}" ${route.name === "terminals" ? 'aria-current="page"' : ""}>${icon("terminal")}<span>${t("Terminais")}</span></a>` : "";
    const groupLabel = link ? "" : t("Terminais abertos");
    this.paint(this.head, headLink + (section ? `<button class="side-heading side-toggle" data-toggle="group:open"
      aria-expanded="${expanded}" aria-controls="side-live" aria-label="${t("Terminais abertos")}" title="${t("Terminais abertos")}">
      ${icon("chevron-right", "side-chevron")}<span>${groupLabel}</span><span class="side-heading-count">${live.length}</span></button>` : ""), force);

    const records = new Map((this.data?.open || []).map((s) => [s.id, s]));
    const { closed = [], closed_total: total = 0 } = this.data || {};
    const rows = live.map(({ info }) => {
      const record = records.get(info.id);
      return this.sessionHtml({
        task_list: [], note_list: [], tags: [], tasks: {}, ...record, ...info, open: true,
      }, active);
    }).join("");
    this.paint(this.body, section ? `
      <section id="side-live" aria-label="${t("Terminais abertos")}" ${expanded || rail ? "" : "hidden"}>
        <div class="tree">${rows || `<div class="tree-empty">${t("Nenhum terminal aberto")}</div>`}</div>
      </section>
      ${terminals.stale ? `<div class="tree-empty" role="status">${t("Lista de terminais desatualizada.")}</div>` : ""}
      <section class="tree" aria-label="${t("Histórico")}">${this.historyHtml(closed, total, active)}</section>` : "", force);
    syncPorts();
  }

  paint(host, html, force) {
    if (!force && host.markup === html) return;
    const old = document.activeElement;
    const had = host.contains(old);
    const row = had && old.closest("[data-id]");
    const attrs = ["data-toggle", "data-menu", "data-identity", "data-port", "href", "data-action"];
    const attr = had && attrs.find((key) => old.hasAttribute(key));
    host.innerHTML = html;
    host.markup = html;
    if (!had) return;
    const scope = row ? host.querySelector(`[data-id="${CSS.escape(row.dataset.id)}"]`) : host;
    const next = attr && scope?.querySelector(`[${attr}="${CSS.escape(old.getAttribute(attr))}"]`);
    if (next) next.focus({ preventScroll: true });
    else this.head.querySelector("[data-toggle], a")?.focus({ preventScroll: true });
  }

  /** Histórico folder: closed sessions in per-day subfolders (the most recent open by default). */
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
      ? folders + (total > closed.length && closed.length < MAX_CLOSED ? `<button class="tree-more" data-action="more">${t("Carregar mais ({n})", { n: total - closed.length })}</button>` : "")
        + (closed.length >= MAX_CLOSED ? `<a class="tree-more" href="#/index">${t("Consultar mais sessões no Índice")}</a>` : "")
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
    const where = s.open && s.cwd ? shortPath(s.cwd) : s.site || "Global";
    const attention = s.open ? labelFor(s.id) : "";
    const popped = s.open && terminals.popped.has(s.id);
    return `
      <div class="tree-node ${s.id === active ? "is-on" : ""} ${s.open ? "is-open" : "is-closed"} ${s.tab_color || s.theme ? `has-theme t-${esc(s.tab_color || s.theme)}` : ""}" data-id="${s.id}" role="${s.open ? "group" : "treeitem"}" aria-expanded="${expanded}">
        <div class="tree-row">
          <button class="tree-twisty" data-toggle="${key}" aria-expanded="${expanded && items > 0}" aria-label="${expanded ? t("Recolher {title}", { title: esc(s.title) }) : t("Expandir {title}", { title: esc(s.title) })}" ${items ? "" : "disabled"}>
            ${items ? icon("chevron-right", "side-chevron") : ""}</button>
          <a class="tree-link" href="${sessionHash(s, "terminal", s.open ? "" : "historico")}" ${s.open ? `data-live="${s.id}"` : ""} ${s.id === active ? 'aria-current="true"' : ""} title="${esc(`${s.title} · ${where}${s.has_doc ? ` · ${t("documentada")}` : ""}`)}">
            ${icon(popped ? "external" : s.open ? "terminal" : "clock")}
            <span class="tree-title">${esc(s.title)}</span>
            <span class="tree-site">${esc(where)}</span>
            ${(s.agents || []).length ? `<span class="tree-agents" title="${t("Sessões de agente pareadas")}">${[...new Set(s.agents.map((a) => a.agent))].map(agentMark).join("")}</span>` : ""}
            ${s.has_doc ? `<span class="tree-doc" title="${t("Tem documentação")}">${icon("book")}</span>` : ""}
            ${attention ? `<span class="dot dot-ok" title="${esc(attention)}" aria-label="${esc(attention)}"></span>` : ""}
            ${progress}
          </a>
          ${s.open ? `<button class="tree-menu-btn live-identity" data-identity="${s.id}" aria-label="${t("Nome e cor da aba")} · ${esc(s.title)}" title="${t("Nome e cor da aba")}">${icon("edit")}</button>` : ""}
          <button class="tree-menu-btn" data-menu="${s.id}" aria-label="${t("Opções da sessão {title}", { title: esc(s.title) })}" title="${t("Opções")}">${icon("dots")}</button>
        </div>
        ${expanded && items ? `<div class="tree-children">
          ${s.task_list.map((t) => `<a class="tree-leaf status-${t.status}" href="${sessionHash(s, "tasks", t.id)}">
              ${icon(t.status === "done" ? "circle-check" : t.status === "doing" ? "circle-half" : "circle")}<span>${esc(t.title)}</span></a>`).join("")}
          ${s.note_list.map((n) => `<a class="tree-leaf" data-note="${esc(n.id)}" aria-haspopup="dialog" href="${sessionHash(s, "notes", n.id)}">
              <span class="tree-swatch swatch-${esc(n.color)}"></span><span>${esc(n.title || t("Post-it sem texto"))}</span></a>`).join("")}
          ${s.tags.length ? `<div class="tree-tags">${s.tags.map((t) => `<a class="chip" style="--chip:${esc(t.color)}" href="${sessionHash(s, "tags", t.id)}">${esc(t.name)}</a>`).join("")}</div>` : ""}
        </div>` : ""}
      </div>`;
  }

  // ── session options ──────────────────────────────────────────────────
  findSession(id) {
    const live = terminals.get(id);
    const record = this.data && [...this.data.open, ...this.data.closed].find((s) => s.id === id);
    if (live?.alive) return { task_list: [], note_list: [], ...record, ...live.info, open: true };
    return record;
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
      ${s.open ? "" : `<button role="menuitem" data-op="rename">${icon("edit")}<span>${t("Renomear")}</span></button>`}
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
        await this.load();
        const trigger = this.root.querySelector(`[data-menu="${CSS.escape(s.id)}"]`);
        await openNote(note.id, trigger);
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
          await patch(`/api/sessions/${s.id}`, { title });
          toast(t("Sessão renomeada para “{title}”.", { title }), { kind: "ok" });
          window.dispatchEvent(new CustomEvent("vulcan-sessions-changed"));
        } catch (err) {
          reportError(err);
        }
      }
      this.body.markup = null;
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
    const identity = event.target.closest("[data-identity]");
    if (identity) {
      editTerminalIdentity(identity.dataset.identity, identity).catch(reportError);
      return;
    }
    const menuBtn = event.target.closest("[data-menu]");
    if (menuBtn) {
      event.preventDefault();
      const rect = menuBtn.getBoundingClientRect();
      this.openMenu(menuBtn.dataset.menu, rect.left, rect.bottom + 4);
      return;
    }
    if (event.target.closest("[data-action='more']")) {
      this.closedLimit = Math.min(MAX_CLOSED, this.closedLimit + PAGE);
      this.load();
      return;
    }
    const toggle = event.target.closest("[data-toggle]");
    if (toggle && this.root.contains(toggle)) {
      event.preventDefault();
      this.toggle(toggle.dataset.toggle);
      this.render(true);
      this.root.querySelector(`[data-toggle="${CSS.escape(toggle.dataset.toggle)}"]`)?.focus({ preventScroll: true });
      return;
    }
    const note = event.target.closest("[data-note]");
    if (note && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) {
      event.preventDefault();
      openNote(note.dataset.note, note).catch(reportError);
      return;
    }
    const link = event.target.closest("a.tree-link");
    if (link) {
      // opening a session also shows its items
      const id = link.closest(".tree-node").querySelector("[data-toggle^='s:']").dataset.toggle;
      if (!this.isOpen(id)) this.toggle(id);
      if (link.dataset.live && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) {
        event.preventDefault();
        this.options.openTerminal(link.dataset.live);
      }
    }
  }
}
