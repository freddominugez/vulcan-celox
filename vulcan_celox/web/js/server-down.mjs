// The local server process ended on its own: the shell says so with the exit code and the last lines of the error
// log. The notice names the cause, says the open terminals ended with it, and offers the log and a restart.

import { isNative, native } from "./api.mjs";
import { $, esc, icon, toast } from "./dom.mjs";
import { t } from "./i18n.mjs";

/** The line that best says why: the last exception line of a traceback, otherwise the last line written. */
export function causeLine(tail) {
  const lines = (tail || []).map((l) => String(l).trim()).filter(Boolean);
  const error = [...lines].reverse().find((l) => /^[A-Za-z_.]*(Error|Exception|Interrupt|Exit)\b/.test(l));
  return error || lines[lines.length - 1] || "";
}

function render(detail) {
  let box = $("#server-down");
  if (!box) {
    box = document.createElement("div");
    box.id = "server-down";
    box.setAttribute("role", "alert");
    document.body.appendChild(box);
  }
  const cause = causeLine(detail.tail);
  box.innerHTML = `
    <p class="sd-title">${icon("alert")}<b>${t("O servidor local parou (código {code}).", { code: esc(detail.code) })}</b></p>
    ${cause ? `<p class="sd-cause mono">${esc(cause)}</p>` : ""}
    <p class="sd-note">${t("Os terminais abertos foram encerrados junto com ele. A memória deles fica guardada, e depois do reinício eles aparecem como encerrados, com Retomar.")}</p>
    ${detail.tail && detail.tail.length ? `<details class="sd-tail"><summary>${t("Últimas linhas do log")}</summary><pre class="mono">${esc(detail.tail.join("\n"))}</pre></details>` : ""}
    <div class="sd-actions">
      <button class="btn btn-sm" data-sd="log">${icon("file-text")}<span>${t("Ver log")}</span></button>
      <button class="btn btn-primary btn-sm" data-sd="restart">${icon("restart")}<span>${t("Reiniciar servidor")}</span></button>
    </div>`;
  box.querySelector("[data-sd=restart]").focus();
}

export function bindServerDown() {
  if (!isNative) return;
  window.addEventListener("vulcan-server-died", (event) => {
    $("#app").classList.add("is-offline", "is-server-down");
    render(event.detail || {});
  });
  window.addEventListener("vulcan-server-restart-failed", (event) => {
    toast(t("O servidor não voltou: {reason}", { reason: String(event.detail || "") }), { kind: "error", timeout: 12000 });
    const button = document.querySelector("[data-sd=restart]");
    if (button) button.disabled = false;
  });
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-sd]");
    if (!button) return;
    if (button.dataset.sd === "log") native({ type: "openServerLog" });
    if (button.dataset.sd === "restart") {
      button.disabled = true;
      native({ type: "restartServer" });
    }
  });
}
