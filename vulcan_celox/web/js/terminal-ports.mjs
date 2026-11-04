// Badge with the ports each tab opened, in the tab bar and in the session list. Click opens in the system browser,
// through the same route as the other links; the app window stays pinned to its own origin.

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

/** Reapplies the badges. Called on every read and after the tab bar or the session list is redrawn. */
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
    /* server restarting: the next round tries again */
  }
}

export function startPorts() {
  poll();
  every(POLL_MS, poll);  // paused while the window is hidden
  // in the capture phase: clicking the badge does not select the tab underneath
  document.addEventListener("click", (event) => {
    const button = event.target.closest && event.target.closest(".port-badge");
    if (!button) return;
    event.stopPropagation();
    event.preventDefault();
    post("/api/open", { kind: "url", target: `http://localhost:${Number(button.dataset.port)}` }).catch(reportError);
  }, true);
}
