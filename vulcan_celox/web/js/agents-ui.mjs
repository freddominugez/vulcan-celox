// Peças comuns das telas de agentes: marca do agente, tempo relativo, trilha de publicação e revisão do índice.

import { every, get, hasBridge, native } from "./api.mjs";
import { esc, toast } from "./dom.mjs";
import { currentLanguage, t } from "./i18n.mjs";

export const AGENT_NAMES = { claude: "Claude Code", codex: "Codex" };
const STEPS = [t("Editou"), "Commit", "Push", "PR"];
const PUB = { none: 1, committed: 2, pushed: 3, pr_open: 4 };

export function agentMark(agent) {
  return `<span class="agent-mark agent-${esc(agent)}" aria-hidden="true">${agent === "claude" ? "C" : "&gt;_"}</span>`;
}

export function agentPill(agent) {
  return `<span class="ag-pill">${agentMark(agent)}${esc(AGENT_NAMES[agent] || agent)}</span>`;
}

export function relTime(iso) {
  if (!iso) return "";
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";
  const s = Math.max(0, (Date.now() - then) / 1000);
  if (s < 60) return t("agora");
  if (s < 3600) return t("há {n} min", { n: Math.round(s / 60) });
  if (s < 86400) return t("há {n} h", { n: Math.round(s / 3600) });
  const d = new Date(then);
  const days = Math.round(s / 86400);
  if (days === 1) return t("ontem");
  if (days < 7) return t("há {n} dias", { n: days });
  return `${d.getDate()}/${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function clock(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function tokens(usage) {
  if (!usage) return "";
  const n = (usage.input || 0) + (usage.output || 0);
  if (n >= 1e6) return t("{n} mi", { n: currentLanguage() === "pt" ? (n / 1e6).toFixed(1).replace(".", ",") : (n / 1e6).toFixed(1) });
  if (n >= 1000) return t("{n} mil", { n: Math.round(n / 1000) });
  return String(n);
}

/** Trilha em 4 etapas: editou, commit, push, PR. A etapa que falta depois da edição fica em alerta. */
export function track(s) {
  const n = s.files_edited || PUB[s.published] > 1 ? PUB[s.published] : 0;
  const label = n ? STEPS[n - 1] : t("nada editado");
  return `<div class="ag-track" role="img" aria-label="${t("Publicação: {label}", { label })}">${STEPS.map((step, i) => {
    const cls = i < n ? "is-done" : i === n && n >= 1 && n < 3 ? "is-stuck" : "";
    const text = cls === "is-stuck" ? (i === 1 ? t("sem commit") : t("sem push")) : step;
    return `<span class="ag-step ${cls}"><span class="ag-bar"></span><span>${text}</span></span>`;
  }).join("")}</div>`;
}

export function relPath(path, root) {
  if (root && path.startsWith(root.replace(/\/$/, "") + "/")) return path.slice(root.replace(/\/$/, "").length + 1);
  return path;
}

export function splitPath(path) {
  const i = path.lastIndexOf("/");
  return i < 0 ? ["", path] : [path.slice(0, i + 1), path.slice(i + 1)];
}

/** Cópia síncrona dentro do clique: o WebKit só libera a área de transferência durante o gesto do usuário. */
function copySync(text) {
  // o campo temporário precisa de foco (com o terminal focado, só selecionar não copia);
  // depois o foco volta para onde estava, e o usuário cola direto no terminal
  const previous = document.activeElement;
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.focus();
  area.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  area.remove();
  if (previous && previous.focus) previous.focus();
  return ok;
}

/** Copia e avisa. Chamar direto no tratador do clique, antes de qualquer await. */
export async function copy(text, message) {
  // no app (macOS e Linux) a casca copia: NSPasteboard ou Gtk.Clipboard, sem depender do WebKit
  let ok = hasBridge && native({ type: "copy", text });
  if (!ok) ok = copySync(text);  // no navegador: o síncrono primeiro, porque depois de um await o clique já passou
  if (!ok && navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch {
      ok = false;
    }
  }
  toast(ok ? message : t("Não deu para copiar. Selecione o texto e use ⌘C."), { kind: ok ? "ok" : "error" });
  return ok;
}

export function emptyAgents(roots) {
  const where = roots ? [...(roots.claude || []), ...(roots.codex || [])].map((r) => `<code>${esc(r)}</code>`).join(` ${t("e")} `) : `~/.claude ${t("e")} ~/.codex`;
  return `<div class="empty-block">
    <h3>${t("Nenhuma sessão de agente ainda")}</h3>
    <p>${t("O Vulcan Celox lê as sessões que o Claude Code e o Codex gravam em {where}, sem chave de API e sem alterar nada lá. Abra o {claude} ou o {codex} num terminal: a sessão aparece aqui em poucos segundos.", { where, claude: "<code>claude</code>", codex: "<code>codex</code>" })}</p>
  </div>`;
}

/** Redesenha sem perder a rolagem: as telas de agentes se atualizam sozinhas a cada mudança do índice. */
export function keepScroll(root, draw) {
  const page = root.querySelector(".page");
  const top = page ? page.scrollTop : 0;
  draw();
  const next = root.querySelector(".page");
  if (next) next.scrollTop = top;
}

/** Consulta a revisão do índice a cada 2 s e chama onChange quando muda. */
export class RevisionWatch {
  constructor(onChange, interval = 2000) {
    this.onChange = onChange;
    this.revision = null;
    this.stopTimer = every(interval, () => this.check());
  }

  seen(revision) {
    this.revision = revision;
  }

  async check() {
    try {
      const data = await get("/api/agents/revision");
      if (this.revision !== null && data.revision !== this.revision) {
        this.revision = data.revision;
        this.onChange();
      } else if (this.revision === null) {
        this.revision = data.revision;
      }
    } catch {
      /* servidor ocupado: tenta no próximo ciclo */
    }
  }

  stop() {
    this.stopTimer();
  }
}

export function loopPrompt(s) {
  return [t("Você rodou \"{command}\" {count} vezes sem commit no branch {branch} (sessão {id}).", { command: s.loop.command, count: s.loop.count, branch: s.branch || t("atual"), id: s.id }),
    t("Pare agora. Em três linhas: a hipótese atual, o que já tentou e o próximo passo diferente."),
    t("Não rode o teste de novo antes de me mostrar isso.")].join(" ");
}

