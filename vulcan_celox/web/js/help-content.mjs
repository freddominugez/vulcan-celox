// Help content: a single place, `help/conteudo.json`, read by the Help screen and by the generator of
// docs/pt-BR/user-guide.md (scripts/manual_md.py). Only loading and text rendering live here.

import { esc } from "./dom.mjs";
import { currentLanguage, keyText } from "./i18n.mjs";

let cache = null;

export async function loadHelp() {
  if (!cache) {
    const res = await fetch(currentLanguage() === "pt" ? "help/conteudo.json" : "help/conteudo.en.json", { cache: "no-store" });
    if (!res.ok) throw new Error(`Ajuda: HTTP ${res.status}`);
    cache = JSON.parse(keyText(await res.text()));
  }
  return cache;
}

/** Text with `code` and **bold**, always escaped first. */
export function inline(text) {
  return esc(text).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
}

export function blockHtml(b) {
  if (b.p) return `<p>${inline(b.p)}</p>`;
  if (b.ul) return `<ul>${b.ul.map((t) => `<li>${inline(t)}</li>`).join("")}</ul>`;
  if (b.passos) return `<ol class="hp-steps">${b.passos.map((t) => `<li>${inline(t)}</li>`).join("")}</ol>`;
  if (b.img) return `<figure class="hp-fig"><img src="img/manual/${esc(b.img)}" alt="${esc(b.alt || "")}" loading="lazy"><figcaption>${esc(b.alt || "")}</figcaption></figure>`;
  if (b.atalhos) return `<dl class="hp-keys">${b.atalhos.map(([k, d]) => `<div><dt><kbd>${esc(k)}</kbd></dt><dd>${esc(d)}</dd></div>`).join("")}</dl>`;
  return "";
}

/** Plain text of a block, for search. */
export function blockText(b) {
  if (b.p) return b.p;
  if (b.ul) return b.ul.join(" ");
  if (b.passos) return b.passos.join(" ");
  if (b.img) return b.alt || "";
  if (b.atalhos) return b.atalhos.map((a) => a.join(" ")).join(" ");
  return "";
}

export function fold(text) {
  return String(text).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
}

// Help section for each screen; every sidebar route must be listed here
export const ROUTE_SECTION = {
  inicio: "primeiros-passos",
  overview: "projetos-php",
  terminals: "terminais",
  node: "node",
  "node-projeto": "node",
  tasks: "organizar",
  notes: "organizar",
  tags: "organizar",
  index: "organizar",
  ambiente: "lerd",
  depuracao: "depuracao",
  agentes: "agentes",
  agente: "agentes",
  "agentes-historico": "agentes",
  "agentes-branches": "agentes",
  "agentes-uso": "custo",
  prompts: "prompts",
  site: "projetos-php",
  ajuda: "primeiros-passos",
  config: "configuracoes",
};

export function sectionFor(route) {
  if (route.name === "site" && route.tab === "harness") return "harness";
  if (route.name === "site" && (route.tab === "debug" || route.tab === "logs")) return "depuracao";
  return ROUTE_SECTION[route.name] || "primeiros-passos";
}
