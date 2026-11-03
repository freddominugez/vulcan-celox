// Estado do PR: pelo gh, se o usuário ligou, ou a estimativa pelos comandos da sessão, sempre dizendo qual é a fonte.

import { get, patch, post } from "./api.mjs";
import { esc, reportError } from "./dom.mjs";
import { t } from "./i18n.mjs";

let enabled = false;

export function prEnabled() {
  return enabled;
}

export async function setPrEnabled(value) {
  const prefs = await patch("/api/preferences", { pr_status: value });
  enabled = prefs.pr_status === true;
  return enabled;
}

export function startPrStatus() {
  patch("/api/preferences", {}).then((prefs) => { enabled = prefs.pr_status === true; }).catch(() => {});
  document.addEventListener("click", (event) => {
    const link = event.target.closest && event.target.closest("[data-pr-url]");
    if (!link) return;
    event.preventDefault();
    post("/api/open", { kind: "url", target: link.dataset.prUrl }).catch(reportError);  // a janela segue presa à origem
  });
}

export function loadPr(query) {
  if (!enabled) return Promise.resolve({ source: "heuristic", reason: "off" });
  return get(`/api/agents/pr?${new URLSearchParams(query)}`).catch(() => ({ source: "heuristic", reason: "failed" }));
}

const STATES = { OPEN: t("aberto"), MERGED: t("integrado"), CLOSED: t("fechado") };
const WHY = {
  off: t("Estimado pelos comandos da sessão."), no_gh: t("Estimado pelos comandos: o gh não está instalado."),
  no_login: t("Estimado pelos comandos: faça gh auth login."), failed: t("Estimado pelos comandos: o gh falhou."),
  timeout: t("Estimado pelos comandos: o gh não respondeu a tempo."), invalid: t("Estimado pelos comandos: resposta do gh não reconhecida."),
  unknown_folder: t("Estimado pelos comandos."),
};

/** Texto puro do estado, para qualquer tela. */
export function prText(data) {
  if (data.source !== "gh") return WHY[data.reason] || WHY.off;
  if (!data.number) return t("Sem PR nesta branch, segundo o GitHub.");
  const parts = [`PR #${data.number}`, data.draft ? t("rascunho") : STATES[data.state] || data.state.toLowerCase()];
  const c = data.checks;
  if (c && c.total) parts.push(c.failed ? t("{n} de {total} checagens falharam", { n: c.failed, total: c.total }) : c.pending ? t("{n} de {total} checagens rodando", { n: c.pending, total: c.total }) : t("{total} checagens ok", { total: c.total }));
  return `${parts.join(" · ")} (GitHub)`;
}

export function prHtml(data) {
  const tone = data.source === "gh" && data.checks && data.checks.failed ? "is-err" : "";
  const text = esc(prText(data));
  return data.source === "gh" && data.url
    ? `<a class="pr-line ${tone}" href="${esc(data.url)}" data-pr-url="${esc(data.url)}">${text}</a>`
    : `<span class="pr-line dim hint ${tone}">${text}</span>`;
}
