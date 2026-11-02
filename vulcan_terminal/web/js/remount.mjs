// vt-29 C4: quando a lista de sites muda, só remonta a tela que recebeu essa lista ao ser montada. As outras
// (Prompts, projetos Node, Agentes, Ajuda...) ficam como estão: remontar perdia o texto digitado no compositor.
// A tela de um site também fica: ela recebe o próprio site, não a lista.

// telas montadas sem a lista de sites; rota desconhecida cai na visão geral, que usa a lista
const KEEP_ON_SITES = new Set([
  "site", "notes", "tags", "index", "agentes", "agente", "agentes-historico", "agentes-branches", "agentes-uso",
  "ajuda", "inicio", "node", "node-projeto", "prompts", "ambiente",
]);

export function remountsOnSites(routeName) {
  return !KEEP_ON_SITES.has(routeName);
}
