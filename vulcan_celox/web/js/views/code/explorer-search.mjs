// Search in file content on the Code screen. Without git the screen says the search needs it. A line of a file is data: always through esc.

import { ApiError, get } from "../../api.mjs";
import { esc } from "../../dom.mjs";
import { t } from "../../i18n.mjs";

export class ExplorerSearch {
  constructor(panel, tree, button, pick) {
    this.panel = panel;
    this.tree = tree;
    this.button = button;
    this.pick = pick;
    this.root = null;
    this.ticket = 0;
    panel.innerHTML = `<form class="ce-searchform" data-ce-searchform><input class="input mono" name="q" spellcheck="false" autocomplete="off" placeholder="${t("Texto a buscar")}" aria-label="${t("Texto a buscar")}"></form>
      <div class="ce-results" data-ce-results aria-live="polite"></div>`;
    this.results = panel.querySelector("[data-ce-results]");
    this.input = panel.querySelector("input");
    panel.querySelector("form").addEventListener("submit", (e) => {
      e.preventDefault();
      this.run();
    });
    this.input.addEventListener("keydown", (e) => {
      if (e.key === "Escape") this.toggle(false);
    });
    this.results.addEventListener("click", (e) => {
      const item = e.target.closest("[data-rel]");
      if (item) this.pick(item.dataset.rel, Number(item.dataset.line));
    });
  }

  setRoot(root) {
    if (root === this.root) return;
    this.root = root;
    this.results.innerHTML = "";
    this.input.value = "";
    this.toggle(false);
  }

  toggle(force) {
    const open = force === undefined ? this.panel.hidden : force;
    this.panel.hidden = !open;
    this.tree.hidden = open;
    this.button.setAttribute("aria-pressed", String(open));
    if (open) this.input.focus();
  }

  note(text) {
    this.results.innerHTML = `<p class="ce-result-note">${esc(text)}</p>`;
  }

  async run() {
    const text = this.input.value;
    if (!text) return;
    const ticket = ++this.ticket;
    this.note(t("Buscando…"));
    let data;
    try {
      data = await get(`/api/files/search?root=${encodeURIComponent(this.root)}&q=${encodeURIComponent(text)}`);
    } catch (err) {
      if (ticket === this.ticket) this.note(err instanceof ApiError ? err.message : t("Não foi possível buscar."));
      return;
    }
    if (ticket !== this.ticket) return;
    if (!data.available) {
      this.note(data.reason === "no_git" ? t("A busca no conteúdo precisa do Git, que não foi encontrado nesta máquina.") : t("A busca no conteúdo precisa de Git, e esta pasta não é um repositório."));
      return;
    }
    if (!data.results.length) {
      this.note(t("Nada encontrado nos arquivos do Git."));
      return;
    }
    let html = data.truncated ? `<p class="ce-result-note">${t("Mostrando só os primeiros resultados.")}</p>` : "";
    let file = null;
    for (const r of data.results) {
      if (r.rel !== file) {
        file = r.rel;
        html += `<div class="ce-result-file mono">${esc(file)}</div>`;
      }
      html += `<button type="button" class="ce-result" data-rel="${esc(r.rel)}" data-line="${r.line}"><span class="ce-result-line">${r.line}</span><span class="ce-result-text">${esc(r.text)}</span></button>`;
    }
    this.results.innerHTML = html;
  }
}
