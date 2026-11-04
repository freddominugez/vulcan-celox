// Interface language. The source text in the code is Portuguese; `t()` returns the translation from the dictionary. Only literal text goes into
// t(), so the test can check the dictionary: variable values go in {nome}, already escaped by the caller.

import { token } from "./api.mjs";

let language = "en";
let dictionary = {};

// outside the browser (modules running in the test) the source text is kept
if (typeof document !== "undefined") {
  try {
    const response = await fetch("/api/i18n", { headers: { "X-Vulcan-Token": token } });
    const data = await response.json();
    language = data.language;
    dictionary = data.dictionary || {};
    document.documentElement.lang = language === "pt" ? "pt-BR" : "en";
  } catch {
    /* server down: the error screen shows with the source text */
  }
}

export function currentLanguage() {
  return language;
}

export function t(text, values) {
  const out = dictionary[text] ?? text;
  return values ? out.replace(/\{(\w+)\}/g, (all, name) => (name in values ? String(values[name]) : all)) : out;
}

/** Fixed texts of index.html: data-i18n on the text, data-i18n-title, -aria-label and -placeholder on the attributes. */
export function translateStatic(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  for (const attr of ["title", "aria-label", "placeholder"]) {
    root.querySelectorAll(`[data-i18n-${attr}]`).forEach((el) => el.setAttribute(attr, t(el.getAttribute(`data-i18n-${attr}`))));
  }
}
