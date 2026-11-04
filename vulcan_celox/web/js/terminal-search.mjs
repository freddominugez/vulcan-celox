// Search inside the active terminal and faithful copy of the output. The bar belongs to the workspace.

import { $ } from "./dom.mjs";
import { t } from "./i18n.mjs";
import { copy } from "./agents-ui.mjs";
import { terminals } from "./terminal-pool.mjs";

const SEARCH_DECORATIONS = {
  matchBackground: "#6b5420", matchBorder: "#f2c14e", matchOverviewRuler: "#f2c14e",
  activeMatchBackground: "#7C3AED", activeMatchBorder: "#B89AFF", activeMatchColorOverviewRuler: "#B89AFF",
};
// control sequences that serialize writes to restore colors and cursor; when copying text, they are removed
const ANSI = /\x1b\[[0-9;?]*[ -\/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b[()][0-9A-Za-z]|\x1b[=>78]/g;

export class TerminalSearch {
  constructor(workspace, bar) {
    this.ws = workspace;
    this.bar = bar;
    this.bind();
  }

  bind() {
    const input = $(".term-search-input", this.bar);
    input.addEventListener("input", () => this.find("type"));
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        this.find(e.shiftKey ? "prev" : "next");
      }
      if (e.key === "Escape") {
        e.preventDefault();
        this.close();
      }
    });
    this.bar.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-search]");
      if (!btn) return;
      if (btn.dataset.search === "close") this.close();
      else this.find(btn.dataset.search);
    });
  }

  target() {
    const session = terminals.get(this.ws.activeId);
    return session && session.search ? session : null;
  }

  open() {
    if (this.ws.mode !== "terminal" || !this.target()) return false;
    this.bar.hidden = false;
    const input = $(".term-search-input", this.bar);
    input.focus();
    input.select();
    if (input.value) this.find("type");
    return true;
  }

  close() {
    this.bar.hidden = true;
    const session = this.target();
    if (session) {
      session.search.clearDecorations();
      session.focus();
    }
  }

  find(direction) {
    const session = this.target();
    const query = $(".term-search-input", this.bar).value;
    const count = $(".term-search-count", this.bar);
    if (!session) return;
    if (this.subscribed !== session) {
      if (this.listener) this.listener.dispose();
      this.listener = session.search.onDidChangeResults(({ resultIndex, resultCount }) => {
        count.textContent = resultCount ? t("{index} de {count}", { index: resultIndex >= 0 ? resultIndex + 1 : "?", count: resultCount }) : t("0 de 0");
      });
      this.subscribed = session;
    }
    if (!query) {
      session.search.clearDecorations();
      count.textContent = "";
      return;
    }
    const options = { incremental: direction === "type", decorations: SEARCH_DECORATIONS };
    if (direction === "prev") session.search.findPrevious(query, options);
    else session.search.findNext(query, options);
  }

  /** Copies the terminal output: serialize joins the lines the terminal wrapped only on screen */
  copyOutput() {
    const session = terminals.get(this.ws.activeId);
    if (!session) return;
    const raw = session.serializer ? session.serializer.serialize({ excludeModes: true, excludeAltBuffer: true }) : "";
    const text = raw.replace(ANSI, "").replace(/\r\n/g, "\n").replace(/[ \t]+$/gm, "").trimEnd();
    copy(text, t("Saída do terminal copiada."));
  }

  dispose() {
    if (this.listener) this.listener.dispose();
  }
}
