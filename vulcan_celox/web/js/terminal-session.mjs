// A terminal tab: the xterm with its addons and the WebSocket connection to the PTY.

import { wsUrl } from "./api.mjs";
import { t } from "./i18n.mjs";
import { watchTerminal } from "./terminal-watch.mjs";
import { TERMINAL_THEME, xtermTheme } from "./themes.mjs";

/** Instance of a vendored addon, or null if the file did not load (the terminal works without it). */
function addon(name) {
  const mod = window[name];
  try {
    return mod && mod[name] ? new mod[name]() : null;
  } catch {
    return null;
  }
}

const encoder = new TextEncoder();

export class Session {
  constructor(info, hooks) {
    this.info = info;
    this.hooks = hooks;
    this.el = document.createElement("div");
    this.el.className = "xterm-host";
    this.term = new window.Terminal({
      fontFamily: 'ui-monospace, "SF Mono", SFMono-Regular, Menlo, monospace',
      fontSize: 13,
      lineHeight: 1.22,
      cursorBlink: true,
      cursorStyle: "bar",
      allowProposedApi: true,  // the unicode API (addon-unicode11) is flagged as proposed in xterm 6
      scrollback: 10000,
      macOptionIsMeta: true,
      theme: xtermTheme(info.theme) || TERMINAL_THEME,
    });
    this.fit = new window.FitAddon.FitAddon();
    this.term.loadAddon(this.fit);
    this.term.loadAddon(new window.WebLinksAddon.WebLinksAddon((_event, uri) => hooks.openUrl(uri)));
    // search with count, correct emoji and accent width, and faithful copy of the output
    this.search = addon("SearchAddon");
    this.serializer = addon("SerializeAddon");
    const unicode = addon("Unicode11Addon");
    for (const a of [this.search, this.serializer, unicode]) if (a) this.term.loadAddon(a);
    if (unicode) this.term.unicode.activeVersion = "11";
    this.term.attachCustomKeyEventHandler((event) => {
      // Cmd shortcuts stay with the app (native menus and palette)
      if (event.metaKey && !["c", "v", "a"].includes(event.key.toLowerCase())) return false;
      return true;
    });
    this.opened = false;
    this.alive = info.alive;
    this.ws = null;
    this.retry = 0;
    this.term.onData((data) => {
      if (this.disconnected) {
        if (data.includes("\r")) this.reconnect();  // Enter on a disconnected tab tries again
        return;
      }
      this.send(encoder.encode(data));
    });
    this.term.onBinary((data) => this.send(Uint8Array.from(data, (c) => c.charCodeAt(0))));
    this.term.onTitleChange((title) => hooks.onTitle(this, title));
    watchTerminal(this.term, info.id);
    this.el.dataset.tabId = info.id;
  }

  mount(container) {
    container.appendChild(this.el);
    if (!this.opened) {
      this.term.open(this.el);
      this.opened = true;
      this.useWebgl();
      this.connect();
    }
    this.resizeSoon();
  }

  /** WebGL rendering when the context exists; if it fails or is lost, falls back to the default renderer. */
  useWebgl() {
    const Webgl = window.WebglAddon && window.WebglAddon.WebglAddon;
    if (!Webgl) return;
    try {
      const webgl = new Webgl();
      webgl.onContextLoss(() => webgl.dispose());
      this.term.loadAddon(webgl);
      this.renderer = "webgl";
    } catch {
      this.renderer = "dom";  // no WebGL: xterm continues with the default renderer
    }
  }

  connect() {
    if (this.ws) return;
    this.term.reset();
    const ws = new WebSocket(wsUrl(`/ws/terminals/${this.info.id}`));
    ws.binaryType = "arraybuffer";
    ws.onopen = () => {
      this.retry = 0;
      this.sendResize();
    };
    ws.onmessage = (event) => {
      if (typeof event.data === "string") {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "exit") {
            this.alive = false;
            this.term.write(`\r\n\x1b[2m[${msg.code != null ? t("processo encerrado com código {code}", { code: msg.code }) : t("processo encerrado")}]\x1b[0m\r\n`);
            this.hooks.onExit(this);
          }
        } catch {
          /* unknown control message */
        }
        return;
      }
      this.term.write(new Uint8Array(event.data));
    };
    ws.onclose = () => {
      this.ws = null;
      if (this.alive && !this.disposed && this.retry < 5) {
        this.retry += 1;
        setTimeout(() => this.connect(), 400 * this.retry);
      } else if (this.alive && !this.disposed) {
        // gave up reconnecting on its own: the tab says what happened instead of staying silent
        this.disconnected = true;
        this.term.write(`\r\n\x1b[33m[${t("conexão com o terminal perdida. Pressione Enter para reconectar.")}]\x1b[0m\r\n`);
        this.hooks.onExit(this);
      }
    };
    this.ws = ws;
  }

  reconnect() {
    this.disconnected = false;
    this.retry = 0;
    this.hooks.onExit(this);
    this.connect();
  }

  send(bytes) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(bytes);
  }

  sendResize() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "resize", rows: this.term.rows, cols: this.term.cols }));
    }
  }

  resizeSoon() {
    requestAnimationFrame(() => {
      if (!this.el.isConnected || this.el.clientWidth < 20) return;
      try {
        this.fit.fit();
        // re-attaching the element to the DOM does not repaint the renderer's lines; force a redraw
        this.term.refresh(0, this.term.rows - 1);
      } catch {
        return;
      }
      this.sendResize();
    });
  }

  focus() {
    this.term.focus();
  }

  dispose() {
    this.disposed = true;
    if (this.ws) this.ws.close();
    this.term.dispose();
    this.el.remove();
  }
}
