// Documentação com IA na interface: confirmação com prévia do que será enviado e acompanhamento das tarefas.

import { get, post } from "./api.mjs";
import { esc, icon, reportError, toast } from "./dom.mjs";

const listeners = new Set();
let polling = null;
let lastStatus = new Map();

/** Avisa quando uma tarefa de IA muda de estado (a árvore e as telas recarregam). */
export function onJobsChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

async function poll() {
  try {
    const data = await get("/api/ai/jobs");
    let changed = false;
    for (const job of data.jobs) {
      const before = lastStatus.get(job.id);
      if (before === "running" && job.status !== "running") {
        changed = true;
        if (job.status === "done") toast(`${job.message[0].toUpperCase()}${job.message.slice(1)}.`, { kind: "ok", timeout: 7000 });
        else toast(`A geração de “${job.label}” falhou: ${job.message}`, { kind: "error", timeout: 12000 });
      }
      lastStatus.set(job.id, job.status);
    }
    if (changed) listeners.forEach((fn) => fn(data));
    if (data.running) polling = setTimeout(poll, 1500);
    else polling = null;
  } catch (err) {
    polling = null;
    reportError(err);
  }
}

export function watchJobs(seed) {
  if (seed) lastStatus.set(seed.id, seed.status);
  if (!polling) polling = setTimeout(poll, 1200);
}

/** Diálogo modal simples. Resolve true ao confirmar. */
export function confirmDialog({ title, body, confirmLabel = "Confirmar", confirmDisabled = false, danger = false, onDecide = null }) {
  return new Promise((resolve) => {
    const backdrop = document.createElement("div");
    backdrop.className = "dialog-backdrop";
    backdrop.innerHTML = `
      <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title">
        <h2 id="dialog-title">${esc(title)}</h2>
        <div class="dialog-body">${body}</div>
        <div class="dialog-actions">
          <button class="btn" data-answer="no">Cancelar</button>
          <button class="btn ${danger ? "btn-danger" : "btn-primary"}" data-answer="yes" ${confirmDisabled ? "disabled" : ""}>${esc(confirmLabel)}</button>
        </div>
      </div>`;
    const finish = (answer) => {
      if (onDecide) onDecide(answer, backdrop); // lê campos do diálogo (ex.: caixa de seleção) antes de fechar
      backdrop.remove();
      document.removeEventListener("keydown", onKey, true);
      resolve(answer);
    };
    const onKey = (e) => {
      if (e.key === "Escape") finish(false);
    };
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) finish(false);
      const button = e.target.closest("[data-answer]");
      if (button && !button.disabled) finish(button.dataset.answer === "yes");
      if (e.target.closest("[data-go]")) finish(false);
    });
    document.addEventListener("keydown", onKey, true);
    document.body.appendChild(backdrop);
    (backdrop.querySelector("[data-answer=yes]:not([disabled])") || backdrop.querySelector("[data-answer=no]")).focus();
  });
}

function previewBody(preview, what) {
  if (!preview.configured) {
    return `<p>Para documentar com IA, cadastre a chave da Anthropic na tela Índice.</p>
      <p><a class="btn btn-sm" href="#/index" data-go="#/index">${icon("book")}<span>Abrir Índice</span></a></p>`;
  }
  const kb = Math.max(1, Math.round(preview.chars / 1000));
  return `
    <p>${what} vai para a Anthropic, modelo <code>${esc(preview.model)}</code>.</p>
    <ul class="dialog-facts">
      <li>${icon("info")}<span>Cerca de ${kb} mil caracteres${preview.truncated ? ", com o registro do terminal cortado nos trechos mais recentes" : ""}.</span></li>
      <li>${icon("lock")}<span>${preview.redactions ? `${preview.redactions} ${preview.redactions === 1 ? "segredo mascarado" : "segredos mascarados"} antes do envio` : "Nenhum segredo reconhecido; o texto é verificado de novo no envio"}.</span></li>
    </ul>
    <p class="dim">O resultado é gravado ao lado da memória e entra no índice geral. Nada é enviado sem este clique.</p>`;
}

/** Fluxo completo para uma sessão: prévia, confirmação, geração e acompanhamento. */
export async function documentSession(sessionId, title) {
  try {
    const preview = await get(`/api/ai/preview/session/${sessionId}`);
    const ok = await confirmDialog({
      title: `Documentar “${title}” com IA`,
      body: previewBody(preview, "A memória desta sessão (comandos, saída do terminal, tarefas, post-its e tags)"),
      confirmLabel: "Gerar documentação",
      confirmDisabled: !preview.configured,
    });
    if (!ok) return null;
    const job = await post(`/api/ai/docs/session/${sessionId}`);
    toast(`Gerando a documentação de “${title}”… pode levar um minuto.`, { timeout: 8000 });
    watchJobs(job);
    return job;
  } catch (err) {
    reportError(err);
    return null;
  }
}

/** Mesmo fluxo para a documentação geral de todas as sessões. */
export async function documentGeneral() {
  try {
    const preview = await get("/api/ai/preview/general");
    const ok = await confirmDialog({
      title: "Gerar a documentação geral com IA",
      body: previewBody(preview, `O resumo de ${preview.stats.sessions} ${preview.stats.sessions === 1 ? "sessão" : "sessões"} (documentações já geradas, comandos, tarefas e post-its)`),
      confirmLabel: "Gerar documentação geral",
      confirmDisabled: !preview.configured,
    });
    if (!ok) return null;
    const job = await post("/api/ai/docs/general");
    toast("Gerando a documentação geral… pode levar alguns minutos.", { timeout: 8000 });
    watchJobs(job);
    return job;
  } catch (err) {
    reportError(err);
    return null;
  }
}
