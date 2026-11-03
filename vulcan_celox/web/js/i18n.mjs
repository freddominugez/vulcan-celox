// Idioma da interface. O texto-fonte no código é o português; `t()` devolve a tradução do dicionário. Só texto literal entra
// em t(), para o teste conseguir conferir o dicionário: valores variáveis vão em {nome}, já escapados por quem chama.

import { token } from "./api.mjs";

let language = "en";
let dictionary = {};

// fora do navegador (módulos rodando no teste) fica o texto-fonte
if (typeof document !== "undefined") {
  try {
    const response = await fetch("/api/i18n", { headers: { "X-Vulcan-Token": token } });
    const data = await response.json();
    language = data.language;
    dictionary = data.dictionary || {};
    document.documentElement.lang = language === "pt" ? "pt-BR" : "en";
  } catch {
    /* servidor fora do ar: a tela de erro aparece com o texto-fonte */
  }
}

export function currentLanguage() {
  return language;
}

export function t(text, values) {
  const out = dictionary[text] ?? text;
  return values ? out.replace(/\{(\w+)\}/g, (all, name) => (name in values ? String(values[name]) : all)) : out;
}

/** Textos fixos do index.html: data-i18n no texto, data-i18n-title, -aria-label e -placeholder nos atributos. */
export function translateStatic(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  for (const attr of ["title", "aria-label", "placeholder"]) {
    root.querySelectorAll(`[data-i18n-${attr}]`).forEach((el) => el.setAttribute(attr, t(el.getAttribute(`data-i18n-${attr}`))));
  }
}
