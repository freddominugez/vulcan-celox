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
  return `<div class="cf-line" data-role="update"><b>${t("Versão")}</b><span class="mono">${esc(info.current)}</span>
    <span class="dim cf-update">${state}</span>
    ${info.newer && info.url ? `<button class="btn btn-primary btn-sm" data-cf-action="update-open">${icon("external")}<span>${t("Ver versão")}</span></button>` : ""}
    <button class="btn btn-ghost btn-sm" data-cf-action="update-check">${icon("restart")}<span>${t("Verificar agora")}</span></button></div>`;
}

const sizeText = (bytes) => (bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`);

export class DataPanel {
  constructor(root, dataDir) {
    this.root = root;
    this.dataDir = dataDir;
    root.addEventListener("click", (e) => this.onClick(e));
    this.load();
  }

  async load() {
    try {
      this.info = await get("/api/data/backup");
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
      <div class="cf-line"><b>${t("Restaurar de")}</b><input class="input mono cf-path-input" data-role="zip" placeholder="${t("Caminho do arquivo .zip")}" spellcheck="false" aria-label="${t("Arquivo do backup")}">
        ${hasBridge ? `<button class="btn btn-ghost btn-sm" data-data="pick-zip">${icon("folder")}<span>${t("Escolher")}</span></button>` : ""}
        <button class="btn btn-sm" data-data="restore">${icon("restart")}<span>${t("Restaurar")}</span></button></div>
      ${this.info.restore_pending ? `<p class="cf-note" data-role="pending">${icon("info")} ${t("Restauração preparada: ela vale quando você reabrir o app.")}</p>` : ""}
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
        if (path) this.root.querySelector("[data-role=zip]").value = path;
      }
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

  async restore() {
    const path = this.root.querySelector("[data-role=zip]").value.trim();
    const ok = await confirmDialog({
      title: t("Restaurar este backup?"),
      body: `<p>${t("Os dados atuais serão trocados pelos do backup quando você reabrir o app, e os terminais abertos serão fechados. Nada é apagado: os dados atuais ficam na pasta .restauros, dentro da pasta de dados.")}</p><p class="mono">${esc(path)}</p>`,
      confirmLabel: t("Restaurar"),
    });
    if (!ok) return;
    this.info = await post("/api/data/restore", { path });
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
