// Aviso do sistema quando um agente espera e a janela está sem foco. O texto é genérico: agente, projeto e estado,
// nunca o conteúdo da conversa nem o que um programa escreveu no terminal.

import { isNative, native, patch, post } from "./api.mjs";
import { ATTENTION_LABELS, attentionCount, onAttention } from "./attention-state.mjs";
import { toast } from "./dom.mjs";
import { t } from "./i18n.mjs";

const AGENT_NAMES = { claude: "Claude Code", codex: "Codex" };
let enabled = true;
let deniedShown = false;

export function noticeText(event) {
  if (event.kind !== "session") return { title: "Vulcan", text: t("Uma aba do terminal pediu atenção") };
  const { agent, project, state } = event.item;
  return { title: AGENT_NAMES[agent] || t("Agente"), text: `${project || t("Sessão")}: ${ATTENTION_LABELS[state] || t("pede atenção")}` };
}

export function noticesEnabled() {
  return enabled;
}

export async function setNoticesEnabled(value) {
  const prefs = await patch("/api/preferences", { attention_notify: value });
  enabled = prefs.attention_notify !== false;
}

export function startNotices() {
  patch("/api/preferences", {}).then((prefs) => { enabled = prefs.attention_notify !== false; }).catch(() => {});
  onAttention((event) => {
    if (!enabled || document.hasFocus()) return;
    const notice = noticeText(event);
    if (isNative) native({ type: "notice", ...notice });
    else post("/api/agents/notice", notice).catch(() => {});
  });
  window.addEventListener("vulcan-attention", () => {
    if (isNative) native({ type: "badge", count: attentionCount() });
  });
  window.addEventListener("vulcan-notice-denied", () => {
    if (deniedShown) return;
    deniedShown = true;
    toast(t("O macOS não autorizou avisos deste app, que não é assinado pela Apple. O número no ícone do Dock continua valendo."), { kind: "info" });
  });
}
