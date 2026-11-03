// Linha do tempo da sessão agrupada por pedido: o que o agente mexeu e rodou em cada um.

import { esc, icon } from "../dom.mjs";
import { clock, relPath, splitPath } from "../agents-ui.mjs";

const FILE_KINDS = { edit: "edit", new: "novo", read: "leu", delete: "apagou" };
const CMD_KINDS = { shell: "shell", test: "teste", publish: "publica" };

function fileRow(sessionId, root, file) {
  const [dir, name] = splitPath(relPath(file.path, root));
  const label = `<span class="ag-kind k-${esc(file.kind)}">${esc(FILE_KINDS[file.kind] || file.kind)}</span>
    <span class="ag-path" title="${esc(file.path)}"><span class="dim">${esc(dir)}</span>${esc(name)}</span>`;
  // o caminho do agente pode ser relativo: o servidor resolve; quem não editou não tem diff de turno
  return file.seq
    ? `<li><a class="turn-diff" href="#/agentes/${encodeURIComponent(sessionId)}/codigo/${encodeURIComponent(file.path)}/t${file.seq}" title="Ver o diff deste pedido">${label}${icon("chevron-right")}</a></li>`
    : `<li>${label}</li>`;
}

function commandRow(cmd) {
  return `<li><span class="ag-kind k-${esc(cmd.kind)}">${esc(CMD_KINDS[cmd.kind] || cmd.kind)}</span>
    <code class="ag-cmd" title="${esc(cmd.text)}">${esc(cmd.text)}</code><span class="ag-time">${esc(clock(cmd.at))}</span></li>`;
}

export function renderTurns(sessionId, root, data) {
  if (!data.turns.length) return `<div class="empty-inline">${icon("info")}<span>Nenhum pedido registrado nesta sessão.</span></div>`;
  return `<div class="turns">${data.turns.map((t) => `<section class="turn" tabindex="-1" data-turn="${t.turn}">
      <header class="turn-head"><span class="turn-n">${t.turn ? `Pedido ${t.turn}` : "Antes do primeiro pedido"}</span><span class="ag-time">${esc(clock(t.at))}</span></header>
      ${t.ask ? `<p class="turn-ask">${esc(t.ask)}</p>` : ""}
      ${t.files.length ? `<ul class="ag-list">${t.files.map((f) => fileRow(sessionId, root, f)).join("")}</ul>` : ""}
      ${t.commands.length ? `<ul class="ag-list">${t.commands.map(commandRow).join("")}</ul>` : ""}
      ${t.commands_total > t.commands.length ? `<p class="dim hint turn-more">Mais ${t.commands_total - t.commands.length} comandos neste pedido.</p>` : ""}
      ${!t.files.length && !t.commands.length ? `<p class="dim hint turn-more">Só conversa, sem arquivos nem comandos.</p>` : ""}
    </section>`).join("")}</div>${data.next !== null ? `<button class="ag-more" data-action="more">Carregar mais</button>` : ""}`;
}

/** Foco no pedido anterior ou seguinte, a partir do que está em foco ou visível. */
export function stepTurn(root, direction) {
  const all = [...root.querySelectorAll(".turn")];
  if (!all.length) return false;
  let at = all.indexOf(document.activeElement && document.activeElement.closest(".turn"));
  if (at < 0) {
    const page = root.querySelector(".page");
    const top = page ? page.getBoundingClientRect().top : 0;
    at = all.findIndex((t) => t.getBoundingClientRect().bottom > top + 1);
  }
  const next = all[Math.max(0, Math.min(all.length - 1, at + direction))];
  next.focus({ preventScroll: true });
  next.scrollIntoView({ block: "start" });
  return true;
}
