// File tree of the Code screen, on Wunderbaum, loaded the first time the screen opens. A file name is data: the
// library puts the title in with textContent, and the icons come from the fixed table below, never from the name.

import { esc, icon } from "../../dom.mjs";
import { t } from "../../i18n.mjs";
import { ancestors } from "./code-live.mjs";
import { GitMarks, gitTitle, showBranch } from "./explorer-git.mjs";

let loading = null;

export function loadWunderbaum() {
  if (window.mar10 && window.mar10.Wunderbaum) return Promise.resolve(window.mar10.Wunderbaum);
  if (!loading) {
    loading = new Promise((resolve, reject) => {
      const css = document.createElement("link");
      css.rel = "stylesheet";
      css.href = "vendor/wunderbaum.css";
      document.head.appendChild(css);
      const script = document.createElement("script");
      script.src = "vendor/wunderbaum.umd.min.js";
      script.onload = () => resolve(window.mar10.Wunderbaum);
      script.onerror = () => {
        loading = null;
        script.remove();
        css.remove();
        reject(new Error(t("a árvore de arquivos não carregou")));
      };
      document.head.appendChild(script);
    });
  }
  return loading;
}

const wbIcon = (name) => `<i class="wb-icon">${icon(name)}</i>`;
const expander = (name, cls = "") => `<i class="wb-expander ${cls}">${icon(name)}</i>`;
const ICON_MAP = {
  error: wbIcon("alert"), loading: expander("circle-half", "ce-spin"), noData: wbIcon("info"),
  expanderExpanded: expander("chevron-down"), expanderCollapsed: expander("chevron-right"), expanderLazy: expander("chevron-right"),
  checkChecked: "", checkUnchecked: "", checkUnknown: "", radioChecked: "", radioUnchecked: "", radioUnknown: "",
  folder: wbIcon("folder"), folderOpen: wbIcon("folder-open"), folderLazy: wbIcon("folder"), doc: wbIcon("file"),
  colSortable: "", colSortAsc: "", colSortDesc: "", colFilter: "", colFilterActive: "", colMenu: "",
};
const CODE = new Set(["php", "phtml", "js", "mjs", "cjs", "jsx", "ts", "tsx", "py", "rb", "go", "rs", "java", "c", "h", "cpp", "swift", "sh",
  "html", "htm", "vue", "css", "scss", "json", "yml", "yaml", "toml", "xml", "sql"]);
const TEXT = new Set(["md", "markdown", "txt", "log", "csv", "rst"]);
const IMAGE = new Set(["png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "icns", "pdf"]);
const ARCHIVE = new Set(["zip", "gz", "tgz", "tar", "bz2", "xz", "7z", "dmg", "deb", "rpm"]);

function fileIcon(entry) {
  if (entry.kind === "link") return wbIcon("link");
  if (entry.sensitive) return wbIcon("file-lock");
  const ext = entry.name.includes(".") ? entry.name.split(".").pop().toLowerCase() : "";
  if (CODE.has(ext)) return wbIcon("file-code");
  if (TEXT.has(ext)) return wbIcon("file-text");
  if (IMAGE.has(ext)) return wbIcon("file-image");
  if (ARCHIVE.has(ext)) return wbIcon("file-zip");
  return wbIcon("file");
}

function toNode(entry) {
  const dir = entry.kind === "dir";
  return {
    title: entry.name, key: entry.rel, lazy: dir && !entry.sensitive,
    classes: `${entry.ignored ? "ce-ignored" : ""} ${entry.bad_name ? "ce-badname" : ""}`.trim(),
    icon: dir ? (entry.sensitive ? wbIcon("lock") : undefined) : fileIcon(entry),
    tooltip: entry.bad_name ? t("Nome de arquivo fora do UTF-8: não abre aqui.") : entry.name,
    entry,
  };
}

/** List of a folder as tree nodes, with a last row saying that it was cut. */
export function folderNodes(listing) {
  const nodes = listing.entries.map(toNode);
  if (!nodes.length && listing.path) {
    nodes.push({ title: t("Pasta vazia"), key: `\0empty:${listing.path}`, icon: wbIcon("info"), classes: "ce-cut", entry: null });
  }
  if (listing.truncated) {
    nodes.push({ title: t("Mostrando {n} de {total} itens desta pasta.", { n: listing.entries.length, total: listing.total }),
      key: `\0cut:${listing.path}`, icon: wbIcon("info"), classes: "ce-cut", entry: null });
  }
  return nodes;
}

export class FileTree {
  constructor(Wunderbaum, el, { load, onOpen, onExpand, marks, label, gitRoot }) {
    this.load = load;
    this.el = el;
    this.onOpen = onOpen;
    this.onExpand = onExpand;
    this.marks = marks;
    this.expanded = new Set();
    this.tree = new Wunderbaum({
      element: el, debugLevel: 1, source: [], iconMap: ICON_MAP, navigationModeOption: "row", header: false,
      strings: { loading: t("Carregando…"), loadError: t("Erro ao carregar"), moreItems: "…", noData: t("Pasta vazia"), breadcrumbDelimiter: " / ", queryResult: "", noMatch: "", matchIndex: "" },
      emptyChildListExpandable: true, quicksearch: true, connectTopBreadcrumb: null, rowHeightPx: 28,
      lazyLoad: (e) => this.load(e.node.key).then((listing) => this.withDeleted(e.node.key, folderNodes(listing))),
      click: (e) => this.clicked(e),
      keydown: (e) => this.keyed(e),
      expand: (e) => this.toggled(e),
      render: (e) => this.paint(e),
    });
    el.setAttribute("aria-label", label);
    this.git = gitRoot ? new GitMarks(gitRoot, (changed) => this.gitChanged(changed)) : null;
  }

  /** A file git still has but the disk lost stays in its folder, struck through. */
  withDeleted(folder, nodes) {
    if (!this.git) return nodes;
    const have = new Set(nodes.map((n) => n.key));
    const ghosts = this.git.deletedIn(folder).filter((rel) => !have.has(rel)).map((rel) => ghostNode(rel));
    return ghosts.length ? [...nodes, ...ghosts].sort((a, b) => order({ data: a, title: a.title }, { data: b, title: b.title })) : nodes;
  }

  gitChanged(changed) {
    showBranch(this.el, this.git.branch);
    for (const rel of changed) {
      const node = this.node(rel);
      const letter = this.git.get(rel);
      if (node && node.data.entry && node.data.entry.ghost && letter !== "D") node.remove();
      else if (!node && letter === "D") {
        const folder = ancestors(rel).pop() || "";
        const holder = folder ? this.node(folder) : this.tree.root;
        if (holder && (holder === this.tree.root || holder.children)) {
          holder.addChildren(ghostNode(rel));
          holder.sort({ cmp: order });
        }
      }
      this.refresh(rel);
    }
  }

  async show(listing) {
    this.expanded.clear();
    await this.tree.load(this.withDeleted("", folderNodes(listing)));
    this.tree.update("structure");
  }

  node(rel) {
    return this.tree.findKey(rel);
  }

  clicked(e) {
    const { node } = e;
    if (!node || !node.data.entry || (e.info && e.info.region === "expander")) return undefined;
    this.pick(node);
    return undefined;
  }

  keyed(e) {
    if (e.eventName !== "Enter" || !e.node || !e.node.data.entry) return undefined;
    this.pick(e.node);
    return false;
  }

  pick(node) {
    const { entry } = node.data;
    if (entry.bad_name || entry.ghost) return;
    if (entry.kind === "dir") {
      if (node.lazy || node.children) node.setExpanded(!node.expanded);
      return;
    }
    this.onOpen(entry.rel);
  }

  toggled(e) {
    const { node, flag } = e;
    if (!node || !node.data.entry) return;
    if (flag) this.expanded.add(node.key);
    else this.expanded.delete(node.key);
    this.onExpand();
  }

  /** The mark and the dot go in a span of their own at the end of the row: the row may be reused for another path. */
  paint(e) {
    const row = e.nodeElem;
    let slot = row.querySelector(".ce-mark");
    if (!slot) {
      slot = document.createElement("span");
      slot.className = "ce-mark";
      row.appendChild(slot);
    }
    const key = e.node.key;
    const item = this.marks.get(key);
    const git = item || !this.git ? "" : this.git.get(key);  // the live mark goes on top of the Git one
    const folded = !e.node.expanded && e.node.data.entry && e.node.data.entry.kind === "dir";
    const inside = !item && !git && folded && (this.marks.hasInside(key) || Boolean(this.git && this.git.hasInside(key)));
    const mark = item ? item.mark : git || (inside ? "•" : "");
    const src = item ? "live" : git ? "git" : "";
    if (slot.dataset.mark !== mark || slot.dataset.src !== src || slot.dataset.who !== (item && item.agent ? item.agent.agent : "")) {
      slot.dataset.mark = mark;
      slot.dataset.src = src;
      slot.dataset.who = item && item.agent ? item.agent.agent : "";
      slot.innerHTML = mark ? `${item && item.agent ? `<span class="ce-who ce-who-${esc(item.agent.agent)}"></span>` : ""}${esc(mark)}` : "";
      slot.title = !mark ? "" : inside ? t("Há mudanças dentro desta pasta") : item ? markTitle(item) : gitTitle(git);
      slot.setAttribute("aria-label", slot.title);
    }
    row.classList.toggle("ce-deleted", Boolean((item && item.mark === "D") || git === "D"));
  }

  /** A new file shows up where it belongs; a deleted one stays in the tree, struck through, until the next opening. */
  applyEvent(event) {
    const key = event.rel;
    const parent = ancestors(key).pop() || null;
    const ghost = this.node(key);
    if (event.change === "added" && ghost && ghost.data.entry && ghost.data.entry.ghost) ghost.data.entry.ghost = false;
    if (event.change === "added" && !this.node(key)) {
      const holder = parent ? this.node(parent) : this.tree.root;
      if (holder && (holder === this.tree.root || holder.children)) {
        const name = key.split("/").pop();
        holder.addChildren(toNode({ name, rel: key, kind: event.kind, size: 0, mtime: 0, sensitive: event.sensitive, ignored: event.ignored }));
        holder.sort({ cmp: order });
      }
    }
    this.refresh(key);
  }

  /** Redraws one path and its folders. */
  refresh(rel) {
    for (const key of [rel, ...ancestors(rel)]) {
      const node = this.node(key);
      if (node) node.update();
    }
  }

  repaint() {
    this.tree.update("data");
  }

  /** Opens the folders down to the file, loading them one by one, and selects it without firing anything. */
  async reveal(rel) {
    for (const folder of ancestors(rel)) {
      const node = this.node(folder);
      if (!node) return;
      if (!node.expanded) await node.setExpanded(true, { noAnimation: true });
    }
    const node = this.node(rel);
    if (node) {
      await node.setActive(true, { noEvents: true });
      node.scrollIntoView();
    }
  }

  focus() {
    this.tree.setFocus();
  }

  destroy() {
    if (this.git) this.git.stop();
    this.tree.destroy();
  }
}

function ghostNode(rel) {
  return toNode({ name: rel.split("/").pop(), rel, kind: "file", size: 0, mtime: 0, ghost: true });
}

function order(a, b) {
  const dirA = a.data.entry && a.data.entry.kind === "dir" ? 0 : 1;
  const dirB = b.data.entry && b.data.entry.kind === "dir" ? 0 : 1;
  if (!a.data.entry) return 1;
  if (!b.data.entry) return -1;
  if (dirA !== dirB) return dirA - dirB;
  return a.title.toLowerCase().localeCompare(b.title.toLowerCase());
}

function markTitle(item) {
  const what = { A: t("Novo desde que a tela abriu"), M: t("Alterado desde que a tela abriu"), D: t("Apagado desde que a tela abriu") }[item.mark];
  return item.agent ? `${what} · ${agentName(item.agent.agent)}` : `${what} · ${t("Mudança no disco")}`;
}

export function agentName(agent) {
  return agent === "codex" ? "Codex" : "Claude Code";
}
