// Lean Markdown renderer for session memories (headings, tables, lists, quotes and code).

import { esc, icon } from "./dom.mjs";

function inline(text) {
  let out = esc(text);
  out = out.replace(/``\s(.+?)\s``|`([^`]+)`/g, (_m, a, b) => `<code>${a || b}</code>`);
  out = out.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/(^|\s)_(.+?)_(?=\s|$|[.,;:])/g, "$1<em>$2</em>");
  out = out.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_m, label, href) => `<a class="md-link" data-href="${href}">${label}</a>`);
  return out;
}

function splitRow(line) {
  return line.replace(/^\||\|$/g, "").split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, "|"));
}

export function renderMarkdown(source) {
  const lines = source.replace(/<!--.*?-->/g, "").split("\n");
  const html = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    // fences also appear indented inside lists (AI-generated documentation)
    const fence = /^(\s*)(`{3,}|~{3,})([\w+-]*)\s*$/.exec(line);
    if (fence) {
      const indent = fence[1].length;
      const body = [];
      i += 1;
      while (i < lines.length && lines[i].trim() !== fence[2]) {
        const raw = lines[i++];
        body.push(raw.slice(Math.min(indent, raw.length - raw.trimStart().length)));
      }
      i += 1;
      html.push(`<pre class="md-code">${esc(body.join("\n"))}</pre>`);
      continue;
    }
    const heading = /^(#{1,5})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      html.push(`<h${level + 1} class="md-h${level}">${inline(heading[2])}</h${level + 1}>`);
      i += 1;
      continue;
    }
    if (line.startsWith("|") && i + 1 < lines.length && /^\|[-|\s:]+\|$/.test(lines[i + 1])) {
      const head = splitRow(line);
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].startsWith("|")) rows.push(splitRow(lines[i++]));
      html.push(`<table class="md-table"><thead><tr>${head.map((h) => `<th>${inline(h)}</th>`).join("")}</tr></thead>
        <tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`);
      continue;
    }
    if (/^>\s?/.test(line)) {
      const body = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) body.push(lines[i++].replace(/^>\s?/, ""));
      html.push(`<blockquote class="md-quote">${body.map(inline).join("<br>")}</blockquote>`);
      continue;
    }
    const ordered = /^(\d+)\.\s+(.*)$/.exec(line);
    if (ordered) {
      const items = [];
      let match = ordered;
      while (match) {
        items.push(match[2]);
        i += 1;
        match = i < lines.length ? /^(\d+)\.\s+(.*)$/.exec(lines[i]) : null;
      }
      html.push(`<ol class="md-list" start="${Number(ordered[1])}">${items.map((item) => `<li>${inline(item)}</li>`).join("")}</ol>`);
      continue;
    }
    if (/^[-*] /.test(line)) {
      const items = [];
      while (i < lines.length && /^[-*] /.test(lines[i])) items.push(lines[i++].slice(2));
      html.push(`<ul class="md-list">${items.map((item) => {
        const box = /^\[( |x)\]\s(.*)$/.exec(item);
        return box
          ? `<li class="md-check ${box[1] === "x" ? "is-done" : ""}"><span class="md-box">${box[1] === "x" ? icon("check") : ""}</span>${inline(box[2])}</li>`
          : `<li>${inline(item)}</li>`;
      }).join("")}</ul>`);
      continue;
    }
    if (line.trim()) html.push(`<p>${inline(line)}</p>`);
    i += 1;
  }
  return html.join("\n");
}
