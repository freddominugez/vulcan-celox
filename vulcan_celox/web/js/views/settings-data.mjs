// Settings: backup, restore, masking what was already saved, and the new version row.

import { confirmDialog } from "../ai.mjs";
import { get, hasBridge, isNative, native, post } from "../api.mjs";
import { esc, icon, reportError, toast } from "../dom.mjs";
import { pickNative } from "../folder-dialog.mjs";
import { t } from "../i18n.mjs";

const REASONS = {
  offline: () => t("Não foi possível consultar: sem conexão."),
  unavailable: () => t("Não foi possível consultar. Enquanto o repositório for privado, a consulta depende do gh com acesso a ele."),
  invalid: () => t("O GitHub respondeu algo que o app não entende."),
};

export function updateRow(info) {
  const state = info.newer ? t("Versão {version} disponível.", { version: esc(info.latest) })
    : info.reason ? (REASONS[info.reason] || REASONS.invalid)()
      : info.latest ? t("Você está na versão mais recente.") : t("Ainda não consultado.");
  return `<div data-role="update"><div class="cf-line"><b>${t("Versão")}</b><span class="mono">${esc(info.current)}</span>
    <span class="dim cf-update">${state}</span>
    ${info.newer && info.url ? `<button class="btn btn-primary btn-sm" data-cf-action="update-open">${icon("external")}<span>${t("Ver versão")}</span></button>` : ""}
    <button class="btn btn-ghost btn-sm" data-cf-action="update-check" title="${t("Consulta o GitHub neste momento, mesmo com o aviso automático desligado.")}">${icon("restart")}<span>${t("Verificar agora")}</span></button></div>
    <p class="dim cf-note">${t("Verificar agora consulta o GitHub neste momento, mesmo com o aviso automático desligado.")}</p></div>`;
}

const COUNTS = [
  ["terminal_sessions", () => t("sessões de terminal")],
  ["tasks", () => t("tarefas")],
  ["notes", () => t("post-its")],
  ["prompts", () => t("prompts")],
  ["memories", () => t("memórias")],
];

const dateText = (value) => {
  const when = value ? new Date(typeof value === "number" ? value * 1000 : value) : null;
  return when && !Number.isNaN(when.getTime()) ? when.toLocaleString() : t("data desconhecida");
};

/** The summary of the chosen zip. Restore only shows up when nothing in it would be refused. */
function inspectBox(info) {
  const notes = info.warnings.map((w) => `<li class="${w.level === "error" ? "cf-check-error" : "cf-check-warn"}">${icon(w.level === "error" ? "alert" : "info")}<span>${esc(w.text)}</span></li>`).join("");
  const counts = info.counts ? COUNTS.map(([key, label]) => `<li><b>${info.counts[key] === null ? "?" : esc(info.counts[key])}</b> ${label()}</li>`).join("")
    + `<li>${info.counts.agent_index ? t("índice de agentes, {size}", { size: sizeText(info.counts.agent_index) }) : t("sem índice de agentes")}</li>` : "";
  return `<div class="cf-check" data-ok="${info.ok ? "1" : "0"}">
    <p class="cf-check-head"><b>${info.ok ? t("Backup conferido") : t("Este backup não pode ser restaurado")}</b>
      <span class="dim">${info.created_at ? t("feito em {date}", { date: esc(dateText(info.created_at)) }) : ""}${info.version ? ` · ${t("versão {version}", { version: esc(info.version) })}` : ""} · ${sizeText(info.size)}</span></p>
    ${counts ? `<ul class="cf-check-counts">${counts}</ul>` : ""}
    ${notes ? `<ul class="cf-check-notes">${notes}</ul>` : ""}
    ${info.ok ? `<div class="cf-line"><button class="btn btn-primary btn-sm" data-data="restore">${icon("restart")}<span>${t("Restaurar")}</span></button></div>` : ""}
  </div>`;
}

/** The copies a restore moved aside, each one can go to the Trash. */
function restoresBox(list) {
  if (!list.length) return "";
  const rows = list.map((r) => `<li class="cf-restore"><span class="mono">${esc(r.name)}</span><span class="dim">${esc(dateText(r.at))} · ${sizeText(r.size)}</span>
    <button class="btn btn-ghost btn-sm" data-data="trash-restore" data-name="${esc(r.name)}">${icon("trash")}<span>${t("Mover para a Lixeira")}</span></button></li>`).join("");
  return `<div class="cf-line"><b>${t("Cópias de restauração")}</b><span class="dim cf-update">${t("Os dados que estavam no app antes de cada restauração, na pasta .restauros.")}</span></div>
    <ul class="cf-restores">${rows}</ul>`;
}

const sizeText = (bytes) => (bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`);

export class DataPanel {
  constructor(root, dataDir) {
    this.root = root;
    this.dataDir = dataDir;
    root.addEventListener("click", (e) => this.onClick(e));
    // another file chosen: the old summary no longer says anything about it
    root.addEventListener("input", (e) => { if (e.target.dataset.role === "zip" && this.inspected) { this.inspected = null; this.root.querySelector("[data-role=inspect]").innerHTML = ""; } });
    this.load();
  }

  async load() {
    try {
      [this.info, { restores: this.restores }] = await Promise.all([get("/api/data/backup"), get("/api/data/restores")]);
      this.render();
    } catch (err) {
      reportError(err);
    }
  }

  render() {
    const last = this.info.last;
    const lastText = last ? t("Último backup: {name}, {size}.", { name: last.path.split(/[\\/]/).pop(), size: sizeText(last.size) }) : t("Nenhum backup feito por aqui ainda.");
    this.root.innerHTML = `
      <p class="dim cf-note">${t("O backup leva todos os dados do app num arquivo .zip: tarefas, post-its, tags, memórias, prompts, preferências e o índice dos agentes. O arquivo não é criptografado: guarde-o em lugar seguro. A chave da Anthropic fica no sistema e não entra.")}</p>
      <div class="cf-line"><b>${t("Salvar em")}</b><input class="input mono cf-path-input" data-role="folder" value="${esc(this.info.folder)}" spellcheck="false" aria-label="${t("Pasta do backup")}">
        ${hasBridge ? `<button class="btn btn-ghost btn-sm" data-data="pick-folder">${icon("folder")}<span>${t("Escolher")}</span></button>` : ""}
        <button class="btn btn-primary btn-sm" data-data="backup">${icon("database")}<span>${t("Fazer backup")}</span></button></div>
      <p class="dim cf-note" data-role="last">${esc(lastText)}</p>
      <div class="cf-line"><b>${t("Restaurar de")}</b><input class="input mono cf-path-input" data-role="zip" placeholder="${t("Caminho do arquivo .zip")}" spellcheck="false" aria-label="${t("Arquivo do backup")}" value="${esc(this.zip || "")}">
        ${hasBridge ? `<button class="btn btn-ghost btn-sm" data-data="pick-zip">${icon("folder")}<span>${t("Escolher")}</span></button>` : ""}
        <button class="btn btn-sm" data-data="inspect">${icon("search")}<span>${t("Conferir")}</span></button></div>
      <div data-role="inspect">${this.inspected ? inspectBox(this.inspected) : ""}</div>
      ${this.info.restore_error ? `<p class="cf-note" role="alert">${icon("alert")} ${esc(this.info.restore_error)}</p>` : ""}
      ${this.info.restore_pending ? `<p class="cf-note" data-role="pending">${icon("info")} ${t("Restauração preparada: ela vale quando você reabrir o app.")}</p>` : ""}
      <div data-role="restores">${restoresBox(this.restores || [])}</div>
      <div class="cf-line"><b>${t("Memórias antigas")}</b><span class="dim cf-update">${t("As memórias novas já saem com segredos mascarados. Isto reescreve as que foram gravadas antes.")}</span>
        <button class="btn btn-sm" data-data="mask">${icon("check")}<span>${t("Mascarar")}</span></button></div>`;
  }

  async onClick(event) {
    const button = event.target.closest("[data-data]");
    if (!button) return;
    event.preventDefault();
    const action = button.dataset.data;
    button.disabled = true;
    try {
      if (action === "pick-folder") {
        const path = await pickNative(this.root.querySelector("[data-role=folder]").value, "backup");
        if (path) this.root.querySelector("[data-role=folder]").value = path;
      }
      if (action === "pick-zip") {
        const path = await pickNative(this.info.folder, "restore");
        if (path) {
          this.root.querySelector("[data-role=zip]").value = path;
          await this.inspect();
        }
      }
      if (action === "inspect") await this.inspect();
      if (action === "trash-restore") await this.trashRestore(button.dataset.name);
      if (action === "backup") await this.backup();
      if (action === "restore") await this.restore();
      if (action === "mask") await this.mask();
    } catch (err) {
      reportError(err);
    } finally {
      button.disabled = false;
    }
  }

  async backup() {
    toast(t("Fazendo o backup..."));
    this.info = await post("/api/data/backup", { folder: this.root.querySelector("[data-role=folder]").value });
    this.render();
    toast(t("Backup salvo: {n} arquivos, {size}.", { n: this.info.created.files, size: sizeText(this.info.created.size) }), { kind: "ok", timeout: 8000 });
  }

  async inspect() {
    const path = this.root.querySelector("[data-role=zip]").value.trim();
    if (!path) {
      toast(t("Escolha o arquivo do backup."), { kind: "error" });
      this.root.querySelector("[data-role=zip]").focus();
      return;
    }
    this.zip = path;
    this.inspected = await post("/api/data/backup/inspect", { path });
    this.root.querySelector("[data-role=inspect]").innerHTML = inspectBox(this.inspected);
  }

  async trashRestore(name) {
    const ok = await confirmDialog({
      title: t("Mover esta cópia para a Lixeira?"),
      body: `<p>${t("São os dados que estavam no app antes de uma restauração. Eles saem da pasta de dados e vão para a Lixeira do sistema, de onde ainda dá para recuperar.")}</p><p class="mono">${esc(name)}</p>`,
      confirmLabel: t("Mover para a Lixeira"),
      danger: true,
    });
    if (!ok) return;
    ({ restores: this.restores } = await post("/api/data/restores/trash", { name }));
    this.root.querySelector("[data-role=restores]").innerHTML = restoresBox(this.restores);
    toast(t("Cópia movida para a Lixeira."), { kind: "ok" });
  }

  async restore() {
    const path = this.inspected && this.inspected.ok ? this.inspected.path : "";
    if (!path) return;
    const ok = await confirmDialog({
      title: t("Restaurar este backup?"),
      body: `<p>${t("Os dados atuais serão trocados pelos do backup quando você reabrir o app, e os terminais abertos serão fechados. Nada é apagado: os dados atuais ficam na pasta .restauros, dentro da pasta de dados.")}</p><p class="mono">${esc(path)}</p>`,
      confirmLabel: t("Restaurar"),
    });
    if (!ok) return;
    this.info = await post("/api/data/restore", { path });
    this.inspected = null;
    this.zip = "";
    this.render();
    toast(t("Backup conferido. Reabra o app para concluir."), {
      timeout: 600000,
      action: isNative ? { label: t("Reabrir agora"), run: () => native({ type: "relaunch" }) } : null,
    });
  }

  async mask() {
    const ok = await confirmDialog({
      title: t("Mascarar as memórias antigas?"),
      body: `<p>${t("Senhas e chaves reconhecidas nas memórias e na lista de comandos são trocadas por [segredo]. Isso não tem volta. Faça um backup antes se quiser guardar o original, e lembre que um backup antigo continua com os segredos.")}</p>`,
      confirmLabel: t("Mascarar"),
    });
    if (!ok) return;
    const done = await post("/api/data/mask-saved", {});
    toast(t("{secrets} segredos mascarados em {files} memórias e {commands} comandos.", done), { kind: "ok", timeout: 8000 });
  }
}
