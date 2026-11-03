// Textos do visor de código: por que algo não aparece e os avisos sobre o diff.

import { esc, icon } from "../../dom.mjs";
import { clock } from "../../agents-ui.mjs";

export const REASONS = {
  missing: ["O arquivo não existe mais", "Ele foi apagado ou movido depois que a sessão tocou nele."],
  sensitive: ["Nome sensível", "Arquivos como .env, chaves e credenciais não são exibidos, nem o diff deles."],
  outside: ["Fora da pasta da sessão", "O visor só abre arquivos dentro da pasta onde a sessão rodou."],
  too_large: ["Arquivo acima de 1 MB", "Abra no editor para ver este arquivo."],
  binary: ["Arquivo binário", "O visor só mostra texto."],
  unreadable: ["Não foi possível abrir", "Não é um arquivo comum ou falta permissão de leitura."],
  root_refused: ["Pasta não aberta no visor", "Esta sessão rodou numa pasta que contém os dados dos agentes, como a pasta pessoal."],
  no_repo: ["Sem repositório git", "A pasta deste arquivo não está num repositório git."],
  no_git: ["Git não encontrado", "Instale o git para comparar com o último commit."],
  no_diff: ["Edição sem diff próprio", "O registro desta edição não traz o texto, ou a linha passa de 5 MB."],
  source_gone: ["Registro da sessão apagado", "O agente removeu o arquivo da sessão, e o conteúdo das edições só existe nele."],
  no_edit: ["Nenhuma edição neste arquivo", "A sessão só leu este arquivo. Compare com o git ou veja o arquivo."],
  invalid: ["Caminho inválido", "Escolha um arquivo na árvore."],
};

export function diffNotes(d, scope) {
  const notes = [];
  if (d.state === "failed") notes.push(["alert", "Esta edição falhou: o arquivo não mudou."]);
  if (d.truncated) notes.push(["alert", "Cortado em 2 MB: o final não aparece."]);
  if (d.replace_all) notes.push(["info", "O agente trocou todas as ocorrências."]);
  if (d.skipped) notes.push(["info", `${d.skipped} edições deste turno não têm diff próprio.`]);
  if (scope !== "git" && !d.complete) notes.push(["info", "Mostra só o trecho editado."]);
  if (d.status === "new") notes.push(["info", "Arquivo novo: ainda não está no último commit."]);
  if (d.status === "deleted") notes.push(["info", "Arquivo apagado depois do último commit."]);
  if (d.at && scope === "edit") notes.push(["clock", `Às ${clock(d.at)}, no pedido ${d.turn}.`]);
  return notes.map(([i, text]) => `<p class="code-note">${icon(i)}<span>${esc(text)}</span></p>`).join("");
}
