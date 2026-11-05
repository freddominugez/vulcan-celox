// Git state of each file in the Code screen tree: changed, new and deleted compared with the last commit, read from the
// index by the server without running anything from the repository. The live marks of the screen go on top of these.

import { get } from "../../api.mjs";
import { esc, icon } from "../../dom.mjs";
import { t } from "../../i18n.mjs";
import { ancestors } from "./code-live.mjs";

const parentOf = (rel) => (rel.includes("/") ? rel.slice(0, rel.lastIndexOf("/")) : "");

const EVERY = 2000;  // the server answers from its cache until its sweep sees a change
const TITLES = {
  M: () => t("Git: alterado desde o último commit"),
  U: () => t("Git: novo, ainda fora do Git"),
  D: () => t("Git: apagado do disco, ainda no Git"),
};

export const gitTitle = (letter) => (TITLES[letter] ? TITLES[letter]() : "");

export class GitMarks {
  constructor(root, onChange) {
    this.root = root;
    this.onChange = onChange;
    this.items = new Map();
    this.inside = new Set();
    this.branch = null;
    this.stopped = false;
    this.timer = null;
    this.onVisible = () => {
      if (!document.hidden && !this.stopped) this.schedule(0);
    };
    document.addEventListener("visibilitychange", this.onVisible);
    this.schedule(0);
  }

  schedule(ms) {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.tick(), ms);
  }

  async tick() {
    if (this.stopped) return;
    try {
      const data = await get(`/api/files/git?root=${encodeURIComponent(this.root)}`);
      if (this.stopped) return;
      this.set(data);
    } catch (_) {
      /* no Git, or the folder went away: the tree keeps the live marks */
    }
    if (!this.stopped && !document.hidden) this.schedule(EVERY);
  }

  set(data) {
    const next = new Map(Object.entries(data.marks || {}));
    const changed = [...new Set([...this.items.keys(), ...next.keys()])].filter((rel) => this.items.get(rel) !== next.get(rel));
    const branchChanged = (data.branch || null) !== this.branch;
    this.items = next;
    this.branch = data.branch || null;
    this.truncated = Boolean(data.truncated);
    this.inside = new Set();
    for (const rel of next.keys()) for (const folder of ancestors(rel)) this.inside.add(folder);
    if (changed.length || branchChanged) this.onChange(changed);
  }

  get(rel) {
    return this.items.get(rel) || "";
  }

  hasInside(folder) {
    return this.inside.has(folder);
  }

  /** Files git still has but the disk no longer has, directly inside `folder` ("" is the root). */
  deletedIn(folder) {
    return [...this.items].filter(([rel, letter]) => letter === "D" && parentOf(rel) === folder).map(([rel]) => rel);
  }

  stop() {
    this.stopped = true;
    clearTimeout(this.timer);
    document.removeEventListener("visibilitychange", this.onVisible);
  }
}

/** The branch next to the tree buttons. */
export function showBranch(treeEl, branch) {
  const bar = treeEl.closest(".ce-side") && treeEl.closest(".ce-side").querySelector(".ce-side-bar");
  if (!bar) return;
  let tag = bar.querySelector(".ce-branch");
  if (!branch) {
    if (tag) tag.remove();
    return;
  }
  if (!tag) {
    tag = document.createElement("span");
    tag.className = "ce-branch mono";
    bar.appendChild(tag);
  }
  tag.title = t("Branch do Git: {branch}", { branch });
  tag.innerHTML = `${icon("branch")}<span>${esc(branch)}</span>`;
}
