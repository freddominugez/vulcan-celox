// Global pool of terminal sessions: survives screen changes and is the source of the tabs.

import { del, get, native, patch, post } from "./api.mjs";
import { reportError } from "./dom.mjs";
import { loadThemes, xtermTheme } from "./themes.mjs";
import { Session } from "./terminal-session.mjs";

export const terminals = {
  sessions: new Map(),
  order: [],
  popped: new Set(),
  listeners: new Set(),
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

  async sync() {
    const data = await get("/api/terminals");
    const ids = new Set(data.terminals.map((t) => t.id));
    for (const info of data.terminals) {
      const current = this.sessions.get(info.id);
      if (current) {
        current.info = info;
      } else {
        this.sessions.set(info.id, new Session(info, this.hooks));
        this.order.push(info.id);
      }
    }
    for (const id of [...this.sessions.keys()]) {
      if (!ids.has(id)) this.drop(id);
    }
    this.emit();
    return this.list();
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
    const session = new Session(info, this.hooks);
    this.sessions.set(info.id, session);
    this.order.push(info.id);
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
  },

  async rename(id, title) {
    const info = await patch(`/api/terminals/${id}`, { title });
    const session = this.sessions.get(id);
    if (session) session.info = info;
    this.emit();
  },

  popout(id) {
    const session = this.sessions.get(id);
    if (!session) return;
    const title = `${session.info.title} · Vulcan Celox`;
    if (!native({ type: "popout", id, title })) {
      window.open(`${location.pathname}#/popout/${id}`, `vulcan-${id}`, "width=900,height=560");
    }
    this.popped.add(id);
    if (session.el.isConnected) session.el.remove();
    this.emit();
  },

  focusPopout(id) {
    native({ type: "focusPopout", id });
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
