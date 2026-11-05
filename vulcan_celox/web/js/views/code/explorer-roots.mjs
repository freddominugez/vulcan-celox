// Top bar of the Code screen: which folder is open, and how to add or remove one. A folder name is data: always through esc.

import { hasBridge, native } from "../../api.mjs";
import { esc, icon } from "../../dom.mjs";
import { t } from "../../i18n.mjs";
import { pickNative } from "../../folder-dialog.mjs";
import { agentName } from "./explorer-tree.mjs";

const GROUPS = () => [["chosen", t("Escolhidas")], ["site", t("Sites")], ["node", t("Projetos Node")], ["session", t("Sessões de agentes")]];

export function rootOptions(roots, current) {
  return GROUPS().map(([id, label]) => {
    const items = roots.filter((r) => r.source === id);
    if (!items.length) return "";
    return `<optgroup label="${esc(label)}">${items.map((r) => `<option value="${esc(r.path)}" ${r.path === current ? "selected" : ""}>${esc(r.name)} · ${esc(r.short)}</option>`).join("")}</optgroup>`;
  }).join("");
}

/** The form to add a folder, used in the empty state and in the bar. */
export function addFolderForm() {
  return `<form class="ce-add" data-ce-add autocomplete="off">
    <label class="ce-add-field"><span class="dim">${t("Pasta do projeto")}</span>
      <input name="path" class="input mono" spellcheck="false" placeholder="${t("/Users/voce/Code/projeto")}"></label>
    ${hasBridge ? `<button type="button" class="btn btn-sm" data-ce="pick">${icon("folder")}<span>${t("Escolher…")}</span></button>` : ""}
    <button type="submit" class="btn btn-primary btn-sm">${icon("plus")}<span>${t("Abrir")}</span></button>
    <p class="ce-add-error" role="alert" data-ce-error hidden></p></form>`;
}

export function noRootsHtml() {
  return `<div class="code-empty ce-first"><h3>${t("Nenhuma pasta para abrir")}</h3>
    <p>${t("Escolha a pasta de um projeto para ver a árvore inteira e acompanhar o que é escrito no disco. Sites, projetos Node e pastas de sessões de agentes aparecem aqui sozinhos.")}</p>
    ${addFolderForm()}</div>`;
}

export function missingHtml(root, removable) {
  return `<div class="code-empty ce-first"><h3>${t("A pasta não existe mais")}</h3><p class="mono ce-path">${esc(root)}</p>
    <p>${t("Ela foi apagada ou movida. Se voltar, a árvore reabre com o botão abaixo.")}</p>
    <div class="ce-actions"><button type="button" class="btn btn-sm" data-ce="retry">${icon("restart")}<span>${t("Tentar de novo")}</span></button>
    ${removable ? `<button type="button" class="btn btn-ghost btn-sm" data-ce="remove">${icon("x")}<span>${t("Tirar da lista")}</span></button>` : ""}</div>
    ${addFolderForm()}</div>`;
}

/** A folder that is not allowed: one the user can add, or one that can never open, with the server's reason. */
export function refusedHtml(root, err, data) {
  if (data.reason === "root_refused" && !data.why) {
    return `<div class="code-empty ce-first"><h3>${t("Esta pasta ainda não está na lista")}</h3>
      <p class="mono ce-path">${esc(root)}</p><p>${t("O app só abre pastas conhecidas ou escolhidas por você.")}</p>
      <button type="button" class="btn btn-primary btn-sm" data-ce="allow" data-path="${esc(root)}">${icon("plus")}<span>${t("Adicionar e abrir")}</span></button></div>`;
  }
  const title = data.reason === "root_refused" ? t("Esta pasta não pode ser aberta") : t("Não foi possível abrir a pasta");
  return `<div class="code-empty ce-first"><h3>${title}</h3><p class="mono ce-path">${esc(root)}</p><p>${esc(err.message)}</p>${addFolderForm()}</div>`;
}

/** Bottom bar: the folder, whether it is being watched in full, and the last change with who made it. */
export function statusHtml(short, full, partial, last) {
  const who = last && (last.agent
    ? `<span class="ce-who ce-who-${esc(last.agent.agent)}"></span>${esc(agentName(last.agent.agent))}` : t("Mudança no disco"));
  return `<span class="mono" title="${esc(full)}">${esc(short)}</span>
    ${partial ? `<span class="ce-status-warn" title="${t("Mudança em pasta recolhida não aparece enquanto a pasta for tão grande.")}">${icon("alert")}${t("Pasta grande: só o que está aberto é observado")}</span>` : ""}
    <span class="spacer"></span>
    ${last ? `<span class="ce-status-who">${who}</span><span class="mono ce-status-file" title="${esc(last.rel)}">${esc(last.rel)}</span>` : ""}`;
}

export async function pickFolder(input) {
  const path = await pickNative(input.value || "~", "code");
  if (path) input.value = path;
  return path;
}

export function setWindowTitle(name) {
  native({ type: "setTitle", title: name ? `${name} · ${t("Código")} · Vulcan Celox` : `${t("Código")} · Vulcan Celox` });
}
