// Conteúdo da Ajuda (vt-26 C2): um lugar só, `help/conteudo.json`, lido pela tela Ajuda e pelo gerador do
// docs/pt-BR/user-guide.md (scripts/manual_md.py). Aqui ficam só a carga e o desenho do texto.

import { esc } from "./dom.mjs";

let cache = null;

export async function loadHelp() {
  if (!cache) {
    const res = await fetch("help/conteudo.json", { cache: "no-store" });
    if (!res.ok) throw new Error(`Ajuda: HTTP ${res.status}`);
    cache = await res.json();
  }
  return cache;
}

/** Texto com `código` e **negrito**, sempre escapado antes. */
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

/** Texto puro de um bloco, para a busca. */
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

// seção da Ajuda de cada tela (vt-26 C3); toda rota da barra lateral precisa estar aqui
export const ROUTE_SECTION = {
  inicio: "primeiros-passos",
  overview: "projetos-php",
  sites: "projetos-php",
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
};

export function sectionFor(route) {
  if (route.name === "site" && route.tab === "harness") return "harness";
  if (route.name === "site" && (route.tab === "debug" || route.tab === "logs")) return "depuracao";
  return ROUTE_SECTION[route.name] || "primeiros-passos";
}
