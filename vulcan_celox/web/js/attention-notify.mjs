// System notification when an agent is waiting and the window is unfocused. The text is generic: agent, project and state,
// never the conversation content nor what a program wrote to the terminal.

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

const TOLD_KEY = "vulcan-notice-denied-told";

function wasTold() {
  try { return localStorage.getItem(TOLD_KEY) === "1"; } catch { return false; }
}

function rememberTold() {
  try { localStorage.setItem(TOLD_KEY, "1"); } catch { /* no storage: it just shows once per run */ }
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
    if (deniedShown || wasTold()) return;  // once per machine: it does not change on the next launch
    deniedShown = true;
    rememberTold();
    toast(t("O macOS não autorizou avisos deste app, que não é assinado pela Apple. O número no ícone do Dock continua valendo."), { kind: "info" });
  });
}
