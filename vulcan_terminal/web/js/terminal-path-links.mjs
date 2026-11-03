// ⌘-clique em caminho no terminal. Reconhece e monta os links; quem existe é o servidor que diz. Sem DOM e sem dependência
// de outro módulo do app, para rodar também no teste.

const PATH = /(?:\.{1,2}\/|\/)?(?:[\w@+~.-]+\/)*[\w@+~.-]*[\w@+~-](?::(\d+)(?::(\d+))?|\((\d+)\))?/g;
const URL_RE = /\b[a-z][a-z0-9+.-]*:\/\/\S+/gi;
const EXTENSION = /\.[A-Za-z][A-Za-z0-9]*$/;
export const MAX_CANDIDATES = 50;

/** Candidatos de uma linha lógica: { path, line, column, start, end }. Número solto e versão não entram. */
export function findPaths(text) {
  const urls = [...text.matchAll(URL_RE)].map((m) => [m.index, m.index + m[0].length]);
  const found = [];
  for (const match of text.matchAll(PATH)) {
    const start = match.index;
    const end = start + match[0].length;
    if (urls.some(([a, b]) => start < b && end > a)) continue;
    const position = match[1] || match[3];
    const suffix = position ? match[0].slice(match[0].search(match[1] ? /:\d/ : /\(\d/)) : "";
    const path = suffix ? match[0].slice(0, -suffix.length) : match[0];
    if (!path.includes("/") && !EXTENSION.test(path)) continue;
    found.push({ path, line: position ? Number(position) : null, column: match[2] ? Number(match[2]) : null, start, end });
    if (found.length >= MAX_CANDIDATES) break;
  }
  return found;
}

/**
 * Texto de uma linha lógica do xterm, juntando as quebras por largura (isWrapped), e o mapa de cada posição para a
 * célula na tela. Caractere largo ocupa duas células, por isso não dá para contar pelo índice da string.
 */
export function logicalLine(buffer, y) {
  let first = y;
  while (first > 0 && buffer.getLine(first) && buffer.getLine(first).isWrapped) first -= 1;
  let last = y;
  while (buffer.getLine(last + 1) && buffer.getLine(last + 1).isWrapped) last += 1;
  let text = "";
  const cells = [];
  for (let row = first; row <= last; row += 1) {
    const line = buffer.getLine(row);
    if (!line) break;
    for (let x = 0; x < line.length; x += 1) {
      const cell = line.getCell(x);
      if (!cell || cell.getWidth() === 0) continue;
      const chars = cell.getChars() || " ";
      for (let i = 0; i < chars.length; i += 1) cells.push({ x, y: row });
      text += chars;
    }
  }
  return { text: text.replace(/\s+$/, ""), cells };
}

/** Link no formato do xterm (coordenadas a partir de 1, fim inclusivo). Só o que o servidor confirmou vira link. */
export function buildLinks(line, candidates, results, y, activate) {
  const links = [];
  for (const candidate of candidates) {
    const result = results[candidate.path];
    if (!result) continue;
    const from = line.cells[candidate.start];
    const to = line.cells[candidate.end - 1];
    if (!from || !to || from.y > y || to.y < y) continue;
    links.push({
      text: line.text.slice(candidate.start, candidate.end),
      range: { start: { x: from.x + 1, y: from.y + 1 }, end: { x: to.x + 1, y: to.y + 1 } },
      decorations: { underline: true, pointerCursor: true },
      activate: (event) => activate(event, { ...result, line: candidate.line, column: candidate.column }),
    });
  }
  return links;
}

/**
 * Provedor do xterm. `modifier()` diz se a tecla está pressionada agora: sem ela não sublinha nem consulta o servidor.
 * `resolve(paths)` devolve { caminho: resultado } só para os que existem.
 */
export function pathLinkProvider(term, { modifier, resolve, activate }) {
  return {
    provideLinks(lineNumber, callback) {
      if (!modifier()) return callback(undefined);
      const y = lineNumber - 1;
      const line = logicalLine(term.buffer.active, y);
      const candidates = findPaths(line.text);
      if (!candidates.length) return callback(undefined);
      return resolve([...new Set(candidates.map((c) => c.path))]).then((results) => {
        const links = buildLinks(line, candidates, results, y, activate);
        callback(links.length ? links : undefined);
      }, () => callback(undefined));
    },
  };
}
