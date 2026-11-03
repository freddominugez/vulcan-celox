// Selo com as portas que cada aba abriu, na barra de abas e na lista de sessões. O clique abre no navegador do sistema,
// pela mesma rota dos outros links; a janela do app continua presa à própria origem.

import { every, get, post } from "./api.mjs";
import { esc, reportError } from "./dom.mjs";
import { t } from "./i18n.mjs";

const POLL_MS = 10000;
let ports = {};

function badge(list) {
  const first = list[0].port;
  const rest = list.length > 1 ? ` +${list.length - 1}` : "";
  const names = list.map((p) => `:${p.port}${p.command ? ` (${p.command})` : ""}`).join(", ");
  return `<button type="button" class="port-badge" data-port="${first}" title="${t("Abrir localhost:{port} no navegador. Portas desta aba: {names}", { port: first, names: esc(names) })}">:${first}${rest}</button>`;
}

/** Reaplica os selos. Chamado a cada leitura e depois que a barra de abas ou a lista de sessões é redesenhada. */
export function syncPorts() {
  document.querySelectorAll(".tab[data-id], .tree-node[data-id]").forEach((node) => {
    const list = ports[node.dataset.id] || [];
    const html = list.length ? badge(list) : "";
    const host = node.querySelector(":scope > .tree-row") || node;
    const current = host.querySelector(":scope > .port-badge");
    if ((current ? current.outerHTML : "") === html) return;
    if (current) current.remove();
    if (!html) return;
    const label = host.querySelector(":scope > .tab-label");
    if (label) label.insertAdjacentHTML("afterend", html);
    else host.insertAdjacentHTML("beforeend", html);
  });
}

async function poll() {
  try {
    ports = (await get("/api/terminals/ports")).ports || {};
    syncPorts();
  } catch {
    /* servidor reiniciando: a próxima volta tenta de novo */
  }
}

export function startPorts() {
  poll();
  every(POLL_MS, poll);  // parado com a janela oculta
  // na captura: o clique no selo não seleciona a aba por baixo
  document.addEventListener("click", (event) => {
    const button = event.target.closest && event.target.closest(".port-badge");
    if (!button) return;
    event.stopPropagation();
    event.preventDefault();
    post("/api/open", { kind: "url", target: `http://localhost:${Number(button.dataset.port)}` }).catch(reportError);
  }, true);
}
