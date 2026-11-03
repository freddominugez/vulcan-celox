// O que a interface usa do CodeMirror 6. Fica disponível como window.CM.
export { EditorView, lineNumbers, highlightActiveLine, highlightActiveLineGutter, drawSelection, Decoration, keymap } from "@codemirror/view";
export { EditorState, Compartment, StateEffect, StateField } from "@codemirror/state";
export { defaultKeymap } from "@codemirror/commands";
export { syntaxHighlighting, defaultHighlightStyle, HighlightStyle, foldGutter, foldKeymap, codeFolding } from "@codemirror/language";
export { tags } from "@lezer/highlight";
export { search, searchKeymap, openSearchPanel, highlightSelectionMatches } from "@codemirror/search";
export { MergeView, unifiedMergeView, getChunks, goToNextChunk, goToPreviousChunk } from "@codemirror/merge";
export { php } from "@codemirror/lang-php";
export { javascript } from "@codemirror/lang-javascript";
export { python } from "@codemirror/lang-python";
export { html } from "@codemirror/lang-html";
export { css } from "@codemirror/lang-css";
export { json } from "@codemirror/lang-json";
export { markdown } from "@codemirror/lang-markdown";
export { sql } from "@codemirror/lang-sql";
export { yaml } from "@codemirror/lang-yaml";
