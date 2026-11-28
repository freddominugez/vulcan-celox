// Global pool of terminal sessions: survives screen changes and is the source of the tabs.

import { del, every, get, native, patch, post } from "./api.mjs";
import { reportError, toast } from "./dom.mjs";
import { t } from "./i18n.mjs";
import { loadThemes, xtermTheme } from "./themes.mjs";
import { Session } from "./terminal-session.mjs";

/** Route to a terminal session or one of its notebook items. */
export function sessionHash(session, tab = "terminal", focus = "") {
  const tail = `${tab}/${encodeURIComponent(session.id)}${focus ? `/${encodeURIComponent(focus)}` : ""}`;
  return session.site ? `#/sites/${encodeURIComponent(session.site)}/${tail}` : `#/terminals/${tail}`;
}

export const terminals = {
  sessions: new Map(),
  order: [],
  popped: new Set(),
  listeners: new Set(),
  popoutWindows: new Map(),
  stale: false,
  revision: 0,
  pending: null,
  hooks: {
    openUrl: (uri) => post("/api/open", { kind: "url", target: uri }).catch(reportError),
    onTitle: () => {},
    onExit: () => terminals.emit(),
  },

  emit() {
    this.listeners.forEach((fn) => fn());
  },

  subscribe(fn) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  },

  watch() {
    every(1500, () => this.sync());
    window.addEventListener("focus", () => this.sync());
    return this.sync();
  },

  sync() {
    if (this.pending) return this.pending;
    const revision = this.revision;
    this.pending = get("/api/terminals").then(({ terminals: items }) => {
      if (revision !== this.revision) return;
      let changed = this.stale;
      this.stale = false;
      const ids = new Set(items.map((info) => info.id));
      for (const info of items) {
        const current = this.get(info.id);
        if (!current) {
          this.sessions.set(info.id, new Session(info, this.hooks));
          this.order.push(info.id);
          changed = true;
          continue;
        }
        current.alive = current.alive && info.alive;
        info.alive = current.alive;
        changed = changed || Object.keys(info).some((key) =>
          key !== "rows" && key !== "cols" && JSON.stringify(info[key]) !== JSON.stringify(current.info[key]));
        current.info = info;
      }
      for (const id of [...this.sessions.keys()]) {
        if (ids.has(id)) continue;
        this.drop(id);
        changed = true;
      }
      for (const [id, popup] of this.popoutWindows) {
        if (!popup.closed) continue;
        this.popoutWindows.delete(id);
        this.popped.delete(id);
        changed = true;
      }
      if (changed) this.emit();
    }).catch(() => {
      if (this.stale) return;
      this.stale = true;
      this.emit();
    }).finally(() => { this.pending = null; }).then(() => this.list());
    return this.pending;
  },

  live(site) {
    return this.list(site).filter((session) => session.alive);
  },

  list(site) {
    return this.order
      .map((id) => this.sessions.get(id))
      .filter((s) => s && (site === undefined || (s.info.site || "") === (site || "")));
  },

  get(id) {
    return this.sessions.get(id);
  },

  async create({ site = null, cwd = null, command = null, title = null, theme = null, agent = null } = {}) {
    const info = await post("/api/terminals", { site, cwd, command, title, theme, agent, rows: 30, cols: 110 });
    this.revision += 1;
    const session = this.get(info.id) || new Session(info, this.hooks);
    this.sessions.set(info.id, session);
    if (!this.order.includes(info.id)) this.order.push(info.id);
    this.emit();
    return session;
  },

  async close(id) {
    let result = null;
    try {
      result = await del(`/api/terminals/${id}`);
    } catch (err) {
      if (err.status !== 404) throw err;
    }
    this.revision += 1;
    this.drop(id);
    this.emit();
    return result;
  },

  drop(id) {
    const session = this.sessions.get(id);
    if (session) session.dispose();
    this.sessions.delete(id);
    this.order = this.order.filter((x) => x !== id);
    this.popped.delete(id);
    this.popoutWindows.delete(id);
  },

  async rename(id, title) {
    return this.updateIdentity(id, { title });
  },

  async updateIdentity(id, changes) {
    const info = await patch(`/api/terminals/${id}`, { ...changes, require_alive: true });
    this.revision += 1;
    const session = this.get(id);
    if (session) {
      session.alive = session.alive && info.alive;
      session.info = { ...info, alive: session.alive };
    }
    this.emit();
    window.dispatchEvent(new CustomEvent("vulcan-sessions-changed"));
  },

  popout(id) {
    const session = this.sessions.get(id);
    if (!session) return;
    const title = `${session.info.title} · Vulcan Celox`;
    if (!native({ type: "popout", id, title })) {
      const popup = window.open(`${location.pathname}#/popout/${id}`, `vulcan-${id}`, "width=900,height=560");
      if (!popup) return;
      this.popoutWindows.set(id, popup);
    }
    this.popped.add(id);
    if (session.el.isConnected) session.el.remove();
    this.emit();
  },

  focusPopout(id) {
    if (native({ type: "focusPopout", id })) return;
    this.popoutWindows.get(id)?.focus();
    toast(t("Se a janela não vier para frente, selecione a janela destacada."), { timeout: 5000 });
  },
};

window.addEventListener("vulcan-popout-closed", (event) => {
  terminals.popped.delete(event.detail);
  terminals.emit();
});

window.addEventListener("vulcan-themes-loaded", () => {
  terminals.list().forEach((s) => {
    const palette = xtermTheme(s.info.theme);
    if (palette) s.term.options.theme = palette;
  });
});
loadThemes();
