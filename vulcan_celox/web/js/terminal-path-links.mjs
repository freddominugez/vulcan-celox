// ⌘-click on a path in the terminal. Recognizes and builds the links; the server says which ones exist. Free of DOM and of dependencies
// on another app module, so it also runs in the test.

const PATH = /(?:\.{1,2}\/|\/)?(?:[\w@+~.-]+\/)*[\w@+~.-]*[\w@+~-](?::(\d+)(?::(\d+))?|\((\d+)\))?/g;
const URL_RE = /\b[a-z][a-z0-9+.-]*:\/\/\S+/gi;
const EXTENSION = /\.[A-Za-z][A-Za-z0-9]*$/;
export const MAX_CANDIDATES = 50;

/** Candidates from a logical line: { path, line, column, start, end }. Bare numbers and versions are excluded. */
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
  * Text of an xterm logical line, joining the width-based wraps (isWrapped), and the map from each position to the
  * on-screen cell. A wide character takes two cells, so you cannot count by string index.
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

/** Link in xterm format (coordinates from 1, inclusive end). Only what the server confirmed becomes a link. */
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
  * xterm provider. `modifier()` says whether the key is pressed right now: without it, nothing is underlined and the server is not queried.
  * `resolve(paths)` returns { path: result } only for those that exist.
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
