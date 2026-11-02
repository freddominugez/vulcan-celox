// Aba Harness do site (vt-23): onde os agentes estão no contrato. Só leitura: o app não muda status de item nem
// roda sensor; quem valida é o sensor do projeto.

import { every, get, post } from "../api.mjs";
import { confirmDialog } from "../ai.mjs";
import { esc, icon, reportError, toast } from "../dom.mjs";
import { copy } from "../agents-ui.mjs";

const REFRESH_MS = 5000;
const STATES = [
  { id: "feito", label: "feito" }, { id: "andamento", label: "em andamento" },
  { id: "bloqueado", label: "bloqueado" }, { id: "pendente", label: "pendente" },
];
const KIND = { repo: "formato do repositório (.harness/)", minimo: "formato mínimo do Harness Vulcan (.vulcan/)" };

export function resumePrompt(info) {
  const c = info.contrato || {};
  const state = info.tipo === "repo" ? ".harness/state.json" : ".vulcan/state/execution.json";
  const next = info.proximo ? ` e continue do item ${info.proximo}` : " e continue do próximo item pendente";
  return `Leia o contrato ${c.caminho || ""} e o estado em ${state}${next}. `
    + "Um item por vez; só marque validado com o sensor do contrato aprovado. Pare e registre o bloqueio se o mesmo erro voltar.";
}

const ACTION = { criar: "criar arquivo novo", bloco: "acrescentar só o bloco marcado (o resto do arquivo não muda)" };

/** Mostra a lista exata de arquivos e o conteúdo de cada um; só grava com a confirmação (vt-23 C3). */
export async function installDialog(site) {
  const base = `/api/sites/${encodeURIComponent(site.name)}/harness/install`;
  const plan = await get(base);
  const body = `<p>Serão gravados em <span class="mono">${esc(site.path)}</span>. Arquivo que já existe nunca é sobrescrito.</p>
    <div class="hs-plan">${plan.arquivos.map((f) => `<details class="hs-file"><summary><span class="mono">${esc(f.caminho)}</span>
      <span class="dim hint">${esc(ACTION[f.acao] || f.acao)}</span></summary><pre class="hs-pre">${esc(f.conteudo)}</pre></details>`).join("")}</div>`;
  const ok = await confirmDialog({ title: "Instalar o harness mínimo", body, confirmLabel: `Criar ${plan.arquivos.length} itens` });
  if (!ok) return false;
  await post(base, { confirm: true });
  return true;
}

const FAIXAS = ["verde", "amarela", "vermelha"];

function taskForm() {
  const row = (n) => `<div class="hs-form-item">
      <span class="mono dim">C${n}</span>
      <select class="select select-sm" data-f="faixa" aria-label="Faixa do item C${n}">${FAIXAS.map((f) => `<option>${f}</option>`).join("")}</select>
      <input class="input" data-f="objetivo" placeholder="objetivo verificável" aria-label="Objetivo do item C${n}">
      <input class="input" data-f="sensor" placeholder="sensor (ex.: build, teste)" aria-label="Sensor do item C${n}"></div>`;
  return `<div class="hs-form">
    <label>Id da tarefa <input class="input mono" data-k="task_id" placeholder="upload-retry" pattern="[a-z0-9][a-z0-9-]*"></label>
    <label>Objetivo <input class="input" data-k="objetivo" placeholder="objetivo em uma frase"></label>
    <div class="hs-form-items">${[1, 2, 3].map(row).join("")}</div>
    <label>Fora <input class="input" data-k="fora" placeholder="o que não será feito agora"></label>
    <label>Escrita <input class="input" data-k="escrita" placeholder="caminhos permitidos"></label>
    <label>Orçamento <input class="input" data-k="orcamento" value="3 tentativas por item"></label>
    <p class="dim hint">APROVAÇÃO fica pendente: só você aprova, editando o arquivo depois de revisar.</p></div>`;
}

/** Formulário do contrato no formato mínimo (vt-23 C4); grava .vulcan/tasks/<id>.md e nunca sobrescreve. */
export async function newTaskDialog(site) {
  let data = null;
  const ok = await confirmDialog({
    title: "Novo contrato", body: taskForm(), confirmLabel: "Criar contrato",
    onDecide: (answer, root) => {
      if (!answer) return;
      data = {};
      root.querySelectorAll("[data-k]").forEach((el) => { data[el.dataset.k] = el.value.trim(); });
      data.itens = [...root.querySelectorAll(".hs-form-item")].map((r) => ({
        faixa: r.querySelector("[data-f=faixa]").value, objetivo: r.querySelector("[data-f=objetivo]").value.trim(),
        sensor: r.querySelector("[data-f=sensor]").value.trim(),
      })).filter((i) => i.objetivo || i.sensor);
    },
  });
  if (!ok || !data) return false;
  const res = await post(`/api/sites/${encodeURIComponent(site.name)}/harness/tasks`, data);
  toast(`Contrato criado em ${res.caminho}`, { kind: "ok" });
  return true;
}

export class HarnessView {
  constructor(root, options) {
    this.root = root;
    this.site = options.site;
    this.onInstall = options.onInstall || installDialog;
    this.key = null;
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.root.innerHTML = `<div class="loading"><span class="skeleton w-40"></span><span class="skeleton w-70"></span></div>`;
    this.stopTimer = every(REFRESH_MS, () => this.load());
    this.load();
  }

  destroy() {
    if (this.stopTimer) this.stopTimer();
  }

  async load() {
    try {
      const info = await get(`/api/sites/${encodeURIComponent(this.site.name)}/harness`);
      const key = `${info.tipo}|${info.estado}|${info.assinatura}`;
      if (key === this.key) return;  // só redesenha quando os arquivos mudam
      this.key = key;
      this.info = info;
      this.render();
    } catch (err) {
      reportError(err);
    }
  }

  render() {
    const info = this.info;
    let body;
    if (info.tipo === "nenhum") body = this.empty(info);
    else if (info.estado !== "ok") {
      body = `<section class="panel hs-panel"><div class="panel-head">${icon("alert")}<h2>Harness ilegível</h2></div>
        <p class="hs-pad">O app não conseguiu ler o estado e não vai fingir que está vazio. Corrija o arquivo no editor.</p>
        <pre class="hs-pre mono">${esc(info.erro || "")}</pre></section>`;
    } else body = this.contract(info);
    this.root.innerHTML = `<div class="page hs-page">${body}</div>`;
  }

  empty(info) {
    return `<section class="panel hs-panel">
      <div class="panel-head">${icon("check-square")}<h2>Sem harness neste projeto</h2></div>
      <p class="hs-pad">Harness é o contrato com itens verificáveis, o estado da execução e o handoff que os agentes leem para
        retomar o trabalho. Nada foi encontrado em <span class="mono">.harness/</span> nem em <span class="mono">.vulcan/</span>.</p>
      ${info.pode_instalar && this.onInstall ? `<div class="hs-pad"><button class="btn btn-primary" data-hs="install">${icon("plus")}<span>Instalar harness</span></button>
        <span class="dim hint">Mostra antes a lista exata de arquivos; nada é sobrescrito.</span></div>` : ""}
    </section>`;
  }

  contract(info) {
    const items = info.itens;
    const count = (id) => items.filter((i) => i.estado === id).length;
    const c = info.contrato || {};
    const bar = items.length ? `<div class="hs-bar" role="img" aria-label="${STATES.map((s) => `${count(s.id)} ${s.label}`).join(", ")}">
        ${items.map((i) => `<span class="hs-seg is-${i.estado}" title="${esc(`${i.id} ${i.titulo}: ${i.estado}`)}"></span>`).join("")}</div>
      <div class="hs-legend">${STATES.map((s) => `<span class="hs-leg"><span class="hs-sw is-${s.id}"></span>${count(s.id)} ${s.label}</span>`).join("")}</div>` : "";
    const rows = items.map((i) => `<li class="hs-item is-${i.estado}">
        <span class="hs-id mono">${esc(i.id)}</span>
        <span class="hs-title">${esc(i.titulo || "(sem título)")}${i.faixa ? ` <span class="ag-pill hs-faixa-${esc(i.faixa)}">${esc(i.faixa)}</span>` : ""}
          ${i.causa ? `<span class="hs-cause">${icon("alert")}${esc(i.causa)}</span>` : ""}
          ${i.evidencia ? `<span class="dim hint mono">${esc(i.evidencia)}</span>` : ""}</span>
        <span class="hs-state">${i.validated ? `${icon("check")}validado` : esc(STATES.find((s) => s.id === i.estado).label)}</span></li>`).join("");
    return `
      <section class="panel hs-panel">
        <div class="panel-head">${icon("check-square")}<h2>${esc(c.id || "Contrato")}</h2>
          ${info.status ? `<span class="ag-pill">${esc(info.status)}</span>` : ""}
          <span class="spacer"></span>
          ${c.absoluto ? `<button class="btn btn-sm" data-hs="open">${icon("edit")}<span>Abrir contrato</span></button>` : ""}
          ${info.tipo === "minimo" ? `<button class="btn btn-sm" data-hs="new-task">${icon("plus")}<span>Novo contrato</span></button>` : ""}
          <button class="btn btn-sm" data-hs="prompt">${icon("copy")}<span>Copiar prompt de retomada</span></button></div>
        <div class="hs-pad hs-facts">
          <span class="dim">${esc(KIND[info.tipo] || info.tipo)}</span>
          ${c.caminho ? `<span class="mono">${esc(c.caminho)}${c.existe ? "" : " (não encontrado)"}</span>` : ""}
          ${c.aprovacao ? `<span>aprovação: <b>${esc(c.aprovacao)}</b></span>` : ""}
          <span>próximo: <b class="mono">${esc(info.proximo || "nenhum")}</b></span>
          <span>último commit verde: <span class="mono">${esc((info.ultimo_commit_verde || "nenhum").slice(0, 12))}</span></span>
        </div>
        ${bar ? `<div class="hs-pad">${bar}</div>` : `<p class="hs-pad dim">Nenhum item no estado.</p>`}
        ${info.bloqueio ? `<p class="hs-pad hs-cause">${icon("alert")}${esc(info.bloqueio)}</p>` : ""}
        <ol class="hs-items">${rows}</ol>
      </section>
      ${info.handoff ? `<section class="panel hs-panel"><div class="panel-head">${icon("note")}<h2>Handoff</h2></div>
        <pre class="hs-pre">${esc(info.handoff.join("\n"))}</pre></section>` : ""}
      ${info.fila && info.fila.length ? `<section class="panel hs-panel"><div class="panel-head">${icon("list")}<h2>Na fila</h2></div>
        <ul class="hs-queue">${info.fila.map((q) => `<li class="mono">${esc(q)}</li>`).join("")}</ul></section>` : ""}
      ${info.tipo === "repo" ? `<p class="dim hint">Este projeto tem harness próprio (.harness/): o app só lê e não instala o formato mínimo aqui.</p>` : ""}`;
  }

  async onClick(event) {
    const btn = event.target.closest("[data-hs]");
    if (!btn) return;
    const action = btn.dataset.hs;
    try {
      if (action === "open") await post("/api/open", { kind: "source", target: this.info.contrato.absoluto });
      if (action === "prompt") await copy(resumePrompt(this.info), "Prompt de retomada copiado");
      if (action === "new-task" && await newTaskDialog(this.site)) { this.key = null; this.load(); }
      if (action === "install" && this.onInstall) {
        const done = await this.onInstall(this.site);
        if (done) { this.key = null; this.load(); }
      }
    } catch (err) {
      reportError(err);
    }
  }
}
