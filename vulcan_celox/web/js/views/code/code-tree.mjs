// Árvore dos arquivos tocados pela sessão. Nome de arquivo é dado: sempre passa por esc.

import { esc, icon } from "../../dom.mjs";
import { t } from "../../i18n.mjs";

const MARKS = { new: t("novo"), edit: t("editado"), read: t("lido"), delete: t("apagado") };

/** Monta a árvore a partir dos caminhos relativos. Pasta com uma só pasta dentro vira um nó só, como `a/b/c`. */
export function buildTree(files) {
  const root = { name: "", dirs: new Map(), files: [] };
  for (const file of files) {
    if (!file.inside) continue;
    const parts = file.rel.split("/");
    const name = parts.pop();
    let node = root;
    for (const part of parts) {
      if (!node.dirs.has(part)) node.dirs.set(part, { name: part, dirs: new Map(), files: [] });
      node = node.dirs.get(part);
    }
    node.files.push({ ...file, name });
  }
  return { tree: compress(root), outside: files.filter((f) => !f.inside) };
}

function compress(node) {
  const dirs = [...node.dirs.values()].map((dir) => {
    let current = compress(dir);
    while (current.dirs.length === 1 && !current.files.length) {
      const only = current.dirs[0];
      current = { ...only, name: `${current.name}/${only.name}` };
    }
    return current;
  });
  dirs.sort((a, b) => a.name.localeCompare(b.name));
  return { name: node.name, dirs, files: [...node.files].sort((a, b) => a.name.localeCompare(b.name)) };
}

function fileRow(file, selected, depth) {
  const mark = MARKS[file.kind] || file.kind;
  return `<button type="button" class="code-file ${file.path === selected ? "is-on" : ""}" data-path="${esc(file.path)}"
      style="--depth:${depth}" title="${esc(file.path)}" aria-current="${file.path === selected}">
    <span class="code-file-name">${esc(file.name || file.rel)}</span>
    ${file.sensitive ? `<span title="${t("Nome sensível: o conteúdo não é exibido")}">${icon("lock")}</span>` : ""}
    ${file.edits > 1 ? `<span class="count">${file.edits}</span>` : ""}
    <span class="ag-kind k-${esc(file.kind)}">${esc(mark)}</span></button>`;
}

function dirRows(node, selected, depth) {
  return node.dirs.map((dir) => `<div class="code-dir" style="--depth:${depth}" title="${esc(dir.name)}">${icon("folder")}<span>${esc(dir.name)}</span></div>
    ${dirRows(dir, selected, depth + 1)}`).join("") + node.files.map((f) => fileRow(f, selected, depth)).join("");
}

export function renderTree(files, selected) {
  const { tree, outside } = buildTree(files);
  return `<div class="code-tree">${dirRows(tree, selected, 0)}
    ${outside.length ? `<div class="code-dir code-outside" title="${t("O visor só abre arquivos dentro da pasta da sessão")}">${icon("lock")}<span>${t("Fora da pasta da sessão")}</span></div>
      ${outside.map((f) => fileRow({ ...f, name: f.rel }, selected, 0)).join("")}` : ""}</div>`;
}
