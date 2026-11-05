// Ways into the Code screen from other screens. The folder and the file go through encodeURIComponent: both are data.

import { icon, esc } from "../../dom.mjs";
import { t } from "../../i18n.mjs";

export function codeHash(root, file = "", line = 0) {
  let hash = "#/codigo";
  if (root) hash += `/${encodeURIComponent(root)}`;
  if (root && file) hash += `/${encodeURIComponent(file)}`;
  if (root && file && line) hash += `/${line}`;
  return hash;
}

/** A link and not a button with a click handler: the route already does everything. */
export function openInCode(root, { cls = "btn btn-sm", disabled = false } = {}) {
  if (!root || disabled) return "";
  return `<a class="${esc(cls)}" href="${esc(codeHash(root))}" data-open-code title="${t("Ver a árvore e o que muda no disco, ao vivo")}">${icon("code")}<span>${t("Abrir em Código")}</span></a>`;
}

export function openInCodeIcon(root, disabled = false) {
  if (!root || disabled) return "";
  return `<a class="icon-btn" href="${esc(codeHash(root))}" data-open-code title="${t("Abrir em Código")}" aria-label="${t("Abrir em Código")}">${icon("tree")}</a>`;
}
