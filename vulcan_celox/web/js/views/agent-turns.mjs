// Session timeline grouped by request: what the agent touched and ran in each one.

import { esc, icon } from "../dom.mjs";
import { t } from "../i18n.mjs";
import { clock, relPath, splitPath } from "../agents-ui.mjs";

const FILE_KINDS = { edit: "edit", new: t("novo"), read: t("leu"), delete: t("apagou") };
const CMD_KINDS = { shell: "shell", test: t("teste"), publish: t("publica") };

function fileRow(sessionId, root, file) {
  const [dir, name] = splitPath(relPath(file.path, root));
  const label = `<span class="ag-kind k-${esc(file.kind)}">${esc(FILE_KINDS[file.kind] || file.kind)}</span>
    <span class="ag-path" title="${esc(file.path)}"><span class="dim">${esc(dir)}</span>${esc(name)}</span>`;
  // the agent's path may be relative: the server resolves it; one that did not edit has no turn diff
  return file.seq
    ? `<li><a class="turn-diff" href="#/agentes/${encodeURIComponent(sessionId)}/codigo/${encodeURIComponent(file.path)}/t${file.seq}" title="${t("Ver o diff deste pedido")}">${label}${icon("chevron-right")}</a></li>`
    : `<li>${label}</li>`;
}

function commandRow(cmd) {
  return `<li><span class="ag-kind k-${esc(cmd.kind)}">${esc(CMD_KINDS[cmd.kind] || cmd.kind)}</span>
    <code class="ag-cmd" title="${esc(cmd.text)}">${esc(cmd.text)}</code><span class="ag-time">${esc(clock(cmd.at))}</span></li>`;
}

export function renderTurns(sessionId, root, data) {
  if (!data.turns.length) return `<div class="empty-inline">${icon("info")}<span>${t("Nenhum pedido registrado nesta sessão.")}</span></div>`;
  return `<div class="turns">${data.turns.map((tn) => `<section class="turn" tabindex="-1" data-turn="${tn.turn}">
      <header class="turn-head"><span class="turn-n">${tn.turn ? t("Pedido {n}", { n: tn.turn }) : t("Antes do primeiro pedido")}</span><span class="ag-time">${esc(clock(tn.at))}</span></header>
      ${tn.ask ? `<p class="turn-ask">${esc(tn.ask)}</p>` : ""}
      ${tn.files.length ? `<ul class="ag-list">${tn.files.map((f) => fileRow(sessionId, root, f)).join("")}</ul>` : ""}
      ${tn.commands.length ? `<ul class="ag-list">${tn.commands.map(commandRow).join("")}</ul>` : ""}
      ${tn.commands_total > tn.commands.length ? `<p class="dim hint turn-more">${t("Mais {n} comandos neste pedido.", { n: tn.commands_total - tn.commands.length })}</p>` : ""}
      ${!tn.files.length && !tn.commands.length ? `<p class="dim hint turn-more">${t("Só conversa, sem arquivos nem comandos.")}</p>` : ""}
    </section>`).join("")}</div>${data.next !== null ? `<button class="ag-more" data-action="more">${t("Carregar mais")}</button>` : ""}`;
}

/** Focus on the previous or next request, from what is focused or visible. */
export function stepTurn(root, direction) {
  const all = [...root.querySelectorAll(".turn")];
  if (!all.length) return false;
  let at = all.indexOf(document.activeElement && document.activeElement.closest(".turn"));
  if (at < 0) {
    const page = root.querySelector(".page");
    const top = page ? page.getBoundingClientRect().top : 0;
    at = all.findIndex((el) => el.getBoundingClientRect().bottom > top + 1);
  }
  const next = all[Math.max(0, Math.min(all.length - 1, at + direction))];
  next.focus({ preventScroll: true });
  next.scrollIntoView({ block: "start" });
  return true;
}
