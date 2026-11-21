// Code viewer texts: why something does not appear, and the warnings about the diff.

import { esc, icon } from "../../dom.mjs";
import { clock } from "../../agents-ui.mjs";
import { currentLanguage, t } from "../../i18n.mjs";

export const REASONS = {
  missing: [t("O arquivo não existe mais"), t("Ele foi apagado ou movido depois que a sessão tocou nele.")],
  sensitive: [t("Nome sensível"), t("Arquivos como .env, chaves e credenciais não são exibidos, nem o diff deles.")],
  outside: [t("Fora da pasta da sessão"), t("O visor só abre arquivos dentro da pasta onde a sessão rodou.")],
  too_large: [t("Arquivo acima de 1 MB"), t("Abra no editor para ver este arquivo.")],
  binary: [t("Arquivo binário"), t("O visor só mostra texto.")],
  unreadable: [t("Não foi possível abrir"), t("Não é um arquivo comum ou falta permissão de leitura.")],
  root_refused: [t("Pasta não aberta no visor"), t("Esta sessão rodou numa pasta que contém os dados dos agentes, como a pasta pessoal.")],
  previous_unavailable: [t("Sem versão anterior disponível"), t("A revisão anterior não está disponível neste repositório local.")],
  no_repo: [t("Sem repositório git"), t("A pasta deste arquivo não está num repositório git.")],
  no_git: [t("Git não encontrado"), t("Instale o git para comparar com o último commit.")],
  no_diff: [t("Edição sem diff próprio"), t("O registro desta edição não traz o texto, ou a linha passa de 5 MB.")],
  source_gone: [t("Registro da sessão apagado"), t("O agente removeu o arquivo da sessão, e o conteúdo das edições só existe nele.")],
  no_edit: [t("Nenhuma edição neste arquivo"), t("A sessão só leu este arquivo. Compare com o git ou veja o arquivo.")],
  invalid: [t("Caminho inválido"), t("Escolha um arquivo na árvore.")],
};

// CodeMirror keeps its phrases in English and the code editor does not import i18n.mjs: in English there is no swap
export function searchPhrases() {
  if (currentLanguage() === "en") return {};
  return {
    Find: t("Buscar"), next: t("próximo"), previous: t("anterior"), all: t("todos"), "match case": t("maiúsculas"), regexp: "regex",
    "by word": t("palavra inteira"), close: t("fechar"), "current match": t("atual"), "on line": t("na linha"),
    "$ unchanged lines": t("$ linhas iguais"), "$ unchanged line": t("$ linha igual"),
  };
}

export function diffNotes(d, scope) {
  const notes = [];
  if (scope === "git" && d.base) notes.push(["info", t("Base Git HEAD {sha}", { sha: d.base.slice(0, 12) })]);
  if (d.state === "failed") notes.push(["alert", t("Esta edição falhou: o arquivo não mudou.")]);
  if (d.truncated) notes.push(["alert", t("Cortado em 2 MB: o final não aparece.")]);
  if (d.replace_all) notes.push(["info", t("O agente trocou todas as ocorrências.")]);
  if (d.skipped) notes.push(["info", t("{n} edições deste turno não têm diff próprio.", { n: d.skipped })]);
  if (scope !== "git" && !d.complete) notes.push(["info", t("Mostra só o trecho editado.")]);
  if (d.status === "new") notes.push(["info", t("Arquivo novo: ainda não está no último commit.")]);
  if (d.status === "deleted") notes.push(["info", t("Arquivo apagado depois do último commit.")]);
  if (d.at && scope === "edit") notes.push(["clock", t("Às {time}, no pedido {n}.", { time: clock(d.at), n: d.turn })]);
  return notes.map(([i, text]) => `<p class="code-note">${icon(i)}<span>${esc(text)}</span></p>`).join("");
}
