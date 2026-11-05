// When the site list changes, only remount the screen that received that list when it was mounted. The others
// (Prompts, Node projects, Agents, Help...) stay as they are: remounting lost the text typed in the composer.
// A site's own screen also stays: it receives the site itself, not the list.

// screens mounted without the site list; an unknown route falls back to the overview, which uses the list
const KEEP_ON_SITES = new Set([
  "site", "notes", "tags", "index", "agentes", "agente", "agentes-historico", "agentes-branches", "agentes-uso",
  "ajuda", "inicio", "node", "node-projeto", "codigo", "prompts", "ambiente",
]);

export function remountsOnSites(routeName) {
  return !KEEP_ON_SITES.has(routeName);
}
