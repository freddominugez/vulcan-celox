// Shell state and sidebar items; split out of app.mjs.

import { route } from "./app.mjs";
import { icon } from "./dom.mjs";
import { t } from "./i18n.mjs";

// One catalog: each `desc` feeds the sidebar hint, the Home cards and the Settings list.
export const NAV = [
  { id: "inicio", label: t("Início"), icon: "home", hash: "#/inicio", desc: t("A tela de abertura: o que falta configurar e o que cada item faz.") },
  { id: "overview", label: t("Visão geral"), icon: "grid", hash: "#/overview", desc: t("Sites, tarefas abertas, terminais e sessões recentes numa página só.") },
  { id: "terminals", label: t("Terminais"), icon: "terminal", hash: "#/terminals", desc: t("Todos os terminais abertos, de todos os projetos, em tela cheia.") },
  { id: "node", label: t("Projetos Node"), icon: "hex", hash: "#/node", routes: ["node", "node-projeto"], desc: t("Apps Next.js, Vite e outros Node: abrir, ligar o servidor e ver os logs.") },
  { id: "tasks", label: t("Tarefas"), icon: "check-square", hash: "#/tasks", desc: t("As tarefas de todos os projetos num lugar só.") },
  { id: "notes", label: t("Post-its"), icon: "note", hash: "#/notes", desc: t("Anotações globais, fora de projeto. As de cada site ficam na página dele.") },
  { id: "tags", label: t("Tags"), icon: "tag", hash: "#/tags", desc: t("Etiquetas para organizar e encontrar sessões de terminal.") },
  { id: "index", label: t("Índice"), icon: "book", hash: "#/index", desc: t("A memória em Markdown de cada terminal fechado e a documentação gerada com IA.") },
  // Lerd has its own item, with its own state; #/ambiente still works
  { id: "ambiente", label: "Lerd", icon: "database", hash: "#/lerd", routes: ["ambiente"], desc: t("Liga e para o ambiente dos sites PHP: PHP, nginx, banco e HTTPS local. É opcional.") },
  { id: "depuracao", label: t("Depuração"), icon: "bolt", hash: "#/depuracao", desc: t("Consultas SQL, dumps, logs e erros dos sites PHP enquanto rodam.") },
];
// Agent panel: Claude Code and Codex sessions read from disk
export const AGENT_NAV = [
  { id: "agentes", label: t("Agentes"), icon: "spark", hash: "#/agentes", routes: ["agentes", "agente"], desc: t("Sessões do Claude Code e do Codex: o que cada uma editou e se chegou a commit, push e PR.") },
  { id: "agentes-historico", label: t("Histórico de agentes"), icon: "history", hash: "#/agentes/historico", desc: t("Busca em pedidos, respostas, comandos e arquivos de todas as sessões dos agentes.") },
  { id: "agentes-branches", label: t("Branches e worktrees"), icon: "tree", hash: "#/agentes/branches", desc: t("Branches e worktrees dos projetos, com o que falta de commit, push e PR.") },
  { id: "agentes-uso", label: t("Uso e custo"), icon: "gauge", hash: "#/agentes/uso", desc: t("Tokens e custo estimado dos agentes, por dia e por projeto.") },
  { id: "prompts", label: t("Prompts"), icon: "text", hash: "#/prompts", desc: t("Instruções prontas, preenchidas com a sessão atual, para mandar ao agente.") },
];
// Help and Settings sit at the end of the sidebar; the Help content goes into the ⌘K search
export const HELP_NAV = [
  { id: "ajuda", label: t("Ajuda"), icon: "help", hash: "#/ajuda", desc: t("Manual de uso, perguntas frequentes e atalhos de teclado.") },
  { id: "config", label: t("Configurações"), icon: "gear", hash: "#/config", desc: t("O que aparece na barra lateral, tema, idioma, avisos e chave da Anthropic."), locked: true },
];
// the lists below the menu, which can also be hidden in Settings
export const SIDE_SECTIONS = [
  { id: "section-sessions", el: "#side-sessions", label: t("Sessões"), desc: t("Terminais abertos e o histórico dos fechados, com a memória de cada um.") },
  { id: "section-sites", el: "#side-sites", label: t("Sites"), desc: t("Lista dos sites PHP, com filtro e favoritos.") },
  { id: "section-node", el: "#side-node", label: t("Projetos Node"), desc: t("Lista dos projetos Node adicionados.") },
];
// stable groups, in fixed order, collapsible (state remembered); the first one and Help, at the end, have no title
export const NAV_GROUPS = [
  { id: "geral", label: "", title: t("Geral"), items: ["inicio", "overview"] },
  { id: "projetos", label: t("Projetos"), items: ["node", "terminals"] },
  { id: "ambiente", label: t("Ambiente"), items: ["ambiente", "depuracao"] },
  { id: "agentes", label: t("Agentes"), items: ["agentes", "prompts", "agentes-uso", "agentes-branches", "agentes-historico"] },
  { id: "organizar", label: t("Organizar"), items: ["tasks", "notes", "tags", "index"] },
  { id: "ajuda", label: "", title: t("Ajuda e ajustes"), items: ["ajuda", "config"] },
];
export const navById = Object.fromEntries([...NAV, ...AGENT_NAV, ...HELP_NAV].map((n) => [n.id, n]));
// Lerd does not run directly on Windows: no item for it there
export const lerdUnavailable = () => Boolean(app.state && app.state.backend && app.state.backend.installable === false && !app.state.backend.available);
export const app = {
  state: null,
  nodeProjects: [],
  view: null,
  route: { name: "overview" },
  siteFilter: "",
  busyService: false,
  autostartPhase: null,
  tree: null,
  current: null,
  panel: null,
};
