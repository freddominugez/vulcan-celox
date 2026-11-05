// File tabs of the Code screen, at most 12, with their state kept per folder. A file name is data: always through esc.

import { esc, icon } from "../../dom.mjs";
import { t } from "../../i18n.mjs";

export const MAX_TABS = 12;

/** Adds a tab keeping the limit: the oldest one that is not the active one leaves. */
export function addTab(list, rel, max = MAX_TABS) {
  if (list.includes(rel)) return list;
  const next = [...list, rel];
  return next.length > max ? next.slice(next.length - max) : next;
}

export class ExplorerTabs {
  constructor(el, { open, empty }) {
    this.el = el;
    this.open = open;
    this.empty = empty;
    this.list = [];
    this.active = null;
    this.root = null;
    el.setAttribute("role", "tablist");
    el.setAttribute("aria-label", t("Arquivos abertos"));
    el.addEventListener("click", (e) => this.clicked(e));
  }

  key() {
    return `vulcan-code-tabs:${this.root}`;
  }

  /** Comes back to the tabs this folder had. */
  load(root) {
    this.root = root;
    let saved = null;
    try {
      saved = JSON.parse(localStorage.getItem(this.key()) || "null");
    } catch (_) { /* no state: starts empty */ }
    const list = saved && Array.isArray(saved.list) ? saved.list.filter((x) => typeof x === "string") : [];
    this.list = list.slice(-MAX_TABS);
    this.active = saved && this.list.includes(saved.active) ? saved.active : null;
    this.render();
  }

  save() {
    try {
      localStorage.setItem(this.key(), JSON.stringify({ list: this.list, active: this.active }));
    } catch (_) { /* applies only now */ }
  }

  add(rel) {
    this.list = addTab(this.list, rel);
    this.active = rel;
    this.save();
    this.render();
  }

  close(rel) {
    const at = this.list.indexOf(rel);
    this.list = this.list.filter((x) => x !== rel);
    if (this.active === rel) {
      this.active = this.list[Math.min(at, this.list.length - 1)] || null;
      this.save();
      this.render();
      if (this.active) this.open(this.active);
      else this.empty();
      return;
    }
    this.save();
    this.render();
  }

  clicked(event) {
    const close = event.target.closest("[data-tab-close]");
    if (close) {
      this.close(close.dataset.tabClose);
      return;
    }
    const tab = event.target.closest("[data-tab-open]");
    if (tab && tab.dataset.tabOpen !== this.active) this.open(tab.dataset.tabOpen);
  }

  render() {
    this.el.innerHTML = this.list.map((rel) => {
      const on = rel === this.active;
      const name = rel.split("/").pop();
      return `<div class="ce-tab ${on ? "is-on" : ""}"><button type="button" class="ce-tab-open mono" role="tab" aria-selected="${on}" data-tab-open="${esc(rel)}" title="${esc(rel)}">${esc(name)}</button>
        <button type="button" class="ce-tab-close" data-tab-close="${esc(rel)}" aria-label="${t("Fechar {name}", { name: esc(name) })}" title="${t("Fechar")}">${icon("x")}</button></div>`;
    }).join("");
    const on = this.el.querySelector(".ce-tab.is-on");
    if (on && on.scrollIntoView) on.scrollIntoView({ block: "nearest", inline: "nearest" });
  }
}
