// O que cada terminal observa além da saída: avisos dos programas e caminhos clicáveis com ⌘.

import { get, isMac, post } from "./api.mjs";
import { attentionTerminal, syncTabs as syncAttention } from "./attention-state.mjs";
import { reportError, toast } from "./dom.mjs";
import { t } from "./i18n.mjs";
import { watchTerminal as watchAttention } from "./terminal-attention.mjs";
import { pathLinkProvider } from "./terminal-path-links.mjs";
import { syncPorts } from "./terminal-ports.mjs";
import { TurnMarks } from "./terminal-turns.mjs";

/** Marcas da barra de abas, depois de ela ser redesenhada. */
export function syncTabs() {
  syncAttention();
  syncPorts();
}

const turns = new Map();
let lastTyped = null;

/** ⌘⇧↑/↓ na aba em foco, ou na última em que se digitou, se ainda estiver na tela. */
export function stepTerminalTurn(direction) {
  const entries = [...turns.entries()].filter(([, e]) => e.term.element && e.term.element.isConnected && e.term.element.offsetParent);
  const focused = entries.find(([, e]) => e.term.element.contains(document.activeElement));
  const entry = focused || entries.find(([id]) => id === lastTyped);
  if (!entry) return false;
  entry[1].marks.step(direction);
  return true;
}

let held = false;
const isModifier = (event) => (isMac ? event.key === "Meta" : event.key === "Control");
const pressed = (event) => (isMac ? event.metaKey : event.ctrlKey);
window.addEventListener("keydown", (e) => { if (isModifier(e)) held = true; }, true);
window.addEventListener("keyup", (e) => { if (isModifier(e)) held = false; }, true);
window.addEventListener("blur", () => { held = false; });  // ⌘Tab: o keyup vai para outro app

export function openTarget(terminal, event, target) {
  if (!pressed(event)) return;
  if (target.sensitive) {
    toast(t("Arquivo com nome sensível: o app não abre."), { kind: "error" });
    return;
  }
  if (target.kind === "dir") {
    post("/api/open", { kind: "finder", target: target.path }).catch(reportError);
  } else if (target.session) {
    const line = target.line ? `/${target.line}` : "";
    location.hash = `#/agentes/${encodeURIComponent(target.session)}/codigo/${encodeURIComponent(target.path)}${line}`;
  } else {
    post("/api/open", { kind: "terminal_file", terminal, target: target.path }).catch(reportError);
  }
}

export function watchTerminal(term, id) {
  watchAttention(term, id, attentionTerminal);
  const marks = new TurnMarks(term, {
    isAgent: () => get(`/api/agents/paired?terminal=${encodeURIComponent(id)}`).then((d) => d.alive),
    warn: () => toast(t("Este agente usa a tela inteira do terminal, sem histórico para navegar. Os pedidos estão em Agentes, na Linha do tempo."), { timeout: 7000 }),
  });
  turns.set(id, { term, marks });
  term.onData((data) => {
    lastTyped = id;
    if (data.includes("\r")) marks.enter();
  });
  term.registerLinkProvider(pathLinkProvider(term, {
    modifier: () => held,
    resolve: (candidates) => post("/api/code/resolve", { terminal: id, candidates }).then((data) => data.results),
    activate: (event, target) => openTarget(id, event, target),
  }));
}
