// Code viewer: read-only CodeMirror 6, loaded the first time the Código tab opens. The content is always data:
// goes in as the editor document, never as HTML.

let loading = null;

export function loadCodeMirror() {
  if (window.CM) return Promise.resolve(window.CM);
  if (!loading) {
    loading = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "vendor/codemirror.js";
      script.onload = () => resolve(window.CM);
      script.onerror = () => {
        loading = null;
        script.remove();
        reject(new Error("o visor de código não carregou"));
      };
      document.head.appendChild(script);
    });
  }
  return loading;
}

const PHRASES = {
  Find: "Buscar", next: "próximo", previous: "anterior", all: "todos", "match case": "maiúsculas", regexp: "regex",
  "by word": "palavra inteira", close: "fechar", "current match": "atual", "on line": "na linha",
  "$ unchanged lines": "$ linhas iguais", "$ unchanged line": "$ linha igual",
};

const LANGUAGES = {
  php: (CM) => CM.php(), javascript: (CM) => CM.javascript(), jsx: (CM) => CM.javascript({ jsx: true }),
  typescript: (CM) => CM.javascript({ typescript: true }), tsx: (CM) => CM.javascript({ typescript: true, jsx: true }),
  python: (CM) => CM.python(), html: (CM) => CM.html(), css: (CM) => CM.css(), json: (CM) => CM.json(),
  markdown: (CM) => CM.markdown(), sql: (CM) => CM.sql(), yaml: (CM) => CM.yaml(),
};

let highlight = null;

function highlightStyle(CM) {
  if (highlight) return highlight;
  const t = CM.tags;
  highlight = CM.syntaxHighlighting(CM.HighlightStyle.define([
    { tag: [t.keyword, t.modifier, t.operatorKeyword, t.controlKeyword], color: "var(--code-keyword)" },
    { tag: [t.string, t.special(t.string), t.regexp], color: "var(--code-string)" },
    { tag: [t.number, t.bool, t.null, t.atom], color: "var(--code-number)" },
    { tag: [t.comment, t.lineComment, t.blockComment, t.docComment], color: "var(--code-comment)", fontStyle: "italic" },
    { tag: [t.function(t.variableName), t.function(t.propertyName), t.labelName], color: "var(--code-function)" },
    { tag: [t.typeName, t.className, t.namespace, t.tagName, t.heading], color: "var(--code-type)" },
    { tag: [t.propertyName, t.attributeName], color: "var(--code-property)" },
    { tag: t.link, textDecoration: "underline" },
    { tag: t.strong, fontWeight: "600" },
    { tag: t.emphasis, fontStyle: "italic" },
  ]));
  return highlight;
}

function extensions(CM, language, phrases = PHRASES) {
  const lang = LANGUAGES[language];
  return [
    CM.EditorState.readOnly.of(true),
    CM.EditorState.phrases.of(phrases),
    CM.lineNumbers(),
    CM.drawSelection(),
    CM.highlightSelectionMatches(),
    CM.search({ top: true }),
    CM.keymap.of([...CM.searchKeymap, ...CM.defaultKeymap]),
    highlightStyle(CM),
    ...(lang ? [lang(CM)] : []),
  ];
}

let lineMarks = null;

/** Lines marked by the Code screen until the next change. Follows the text if something above them changes. */
function lineMarksField(CM) {
  if (lineMarks) return lineMarks;
  const set = CM.StateEffect.define();
  const field = CM.StateField.define({
    create: () => CM.Decoration.none,
    update(marks, tr) {
      let next = marks.map(tr.changes);
      for (const effect of tr.effects) if (effect.is(set)) next = effect.value;
      return next;
    },
    provide: (f) => CM.EditorView.decorations.from(f),
  });
  lineMarks = { set, field, line: CM.Decoration.line({ class: "ce-changed-line" }) };
  return lineMarks;
}

/** New content in the same editor, changing only the stretch that differs: scroll and selection stay, and the changed lines light up. */
export function updateFile(CM, viewer, next, lines = [], { reveal = false } = {}) {
  const view = viewer.editor;
  const { set, line } = lineMarksField(CM);
  const current = view.state.doc.toString();
  let start = 0;
  const shortest = Math.min(current.length, next.length);
  while (start < shortest && current[start] === next[start]) start += 1;
  let endA = current.length;
  let endB = next.length;
  while (endA > start && endB > start && current[endA - 1] === next[endB - 1]) {
    endA -= 1;
    endB -= 1;
  }
  const changes = current === next ? [] : { from: start, to: endA, insert: next.slice(start, endB) };
  const doc = CM.EditorState.create({ doc: next }).doc;
  const ranges = lines.filter((n) => n >= 1 && n <= doc.lines).map((n) => line.range(doc.line(n).from));
  const effects = [set.of(CM.Decoration.set(ranges))];
  if (reveal && ranges.length) effects.push(CM.EditorView.scrollIntoView(ranges[0].from, { y: "center" }));
  view.dispatch({ changes, effects });
}

/** Whole file. `setText` swaps the content without remounting, and `reveal` scrolls to the range and marks it. */
export function mountFile(CM, parent, text, language, phrases) {
  const view = new CM.EditorView({ parent, state: CM.EditorState.create({ doc: text, extensions: [...extensions(CM, language, phrases), lineMarksField(CM).field] }) });
  return {
    editor: view,
    setText(next) {
      if (next !== view.state.doc.toString()) view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: next } });
    },
    reveal(snippet) {
      const at = findSnippet(view.state.doc.toString(), snippet);
      if (at < 0) return false;
      view.dispatch({ selection: { anchor: at, head: at + lastPiece(snippet).length },
                      effects: CM.EditorView.scrollIntoView(at, { y: "center" }) });
      return true;
    },
    /** Goes to a line, with the cursor on it. */
    line(number) {
      if (!number) return;
      const line = view.state.doc.line(Math.min(Math.max(1, number), view.state.doc.lines));
      view.dispatch({ selection: { anchor: line.from }, effects: CM.EditorView.scrollIntoView(line.from, { y: "center" }) });
    },
    destroy: () => view.destroy(),
  };
}

function lastPiece(snippet) {
  const pieces = (snippet || "").split("\n…\n");
  return pieces[pieces.length - 1];
}

/** Position of the edited range. The last piece is the most recent; without it, the first non-empty line. */
export function findSnippet(text, snippet) {
  const piece = lastPiece(snippet);
  if (!piece) return -1;
  const at = text.indexOf(piece);
  if (at >= 0) return at;
  const line = piece.split("\n").find((l) => l.trim());
  return line ? text.indexOf(line) : -1;
}

/** Diff: side by side or unified, with the equal parts collapsed. */
export function mountDiff(CM, parent, { old, current, language, layout, phrases }) {
  const base = extensions(CM, language, phrases);
  const collapse = { margin: 3, minSize: 6 };
  if (layout === "unified") {
    const view = new CM.EditorView({ parent, state: CM.EditorState.create({ doc: current, extensions: [
      ...base, CM.unifiedMergeView({ original: old, mergeControls: false, collapseUnchanged: collapse }),
    ] }) });
    return { editor: view, destroy: () => view.destroy() };
  }
  const merge = new CM.MergeView({ parent, a: { doc: old, extensions: base }, b: { doc: current, extensions: base }, collapseUnchanged: collapse });
  return { editor: merge.b, destroy: () => merge.destroy() };
}

export function openSearch(CM, viewer) {
  if (!viewer) return;
  viewer.editor.focus();
  CM.openSearchPanel(viewer.editor);
}
