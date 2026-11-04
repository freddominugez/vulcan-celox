// Shell state and sidebar items; split out of app.mjs.

import { route } from "./app.mjs";
import { icon } from "./dom.mjs";
import { t } from "./i18n.mjs";

export const NAV = [
  { id: "inicio", label: t("Início"), icon: "home", hash: "#/inicio" },
  { id: "overview", label: t("Visão geral"), icon: "grid", hash: "#/overview" },
  // shortcut of the Projects group to the PHP sites (the list stays in the Sites section, separate from Node)
  { id: "sites", label: t("Sites PHP"), icon: "globe", hash: "#/overview", routes: ["site"] },
  { id: "terminals", label: t("Terminais"), icon: "terminal", hash: "#/terminals" },
  { id: "node", label: t("Projetos Node"), icon: "hex", hash: "#/node", routes: ["node", "node-projeto"] },
  { id: "tasks", label: t("Tarefas"), icon: "check-square", hash: "#/tasks" },
  { id: "notes", label: t("Post-its"), icon: "note", hash: "#/notes" },
  { id: "tags", label: t("Tags"), icon: "tag", hash: "#/tags" },
  { id: "index", label: t("Índice"), icon: "book", hash: "#/index" },
  // Lerd has its own item, with its own state; #/ambiente still works
  { id: "ambiente", label: "Lerd", icon: "database", hash: "#/lerd", routes: ["ambiente"] },
  { id: "depuracao", label: t("Depuração"), icon: "bolt", hash: "#/depuracao" },
];
// Agent panel: Claude Code and Codex sessions read from disk
export const AGENT_NAV = [
  { id: "agentes", label: t("Agentes"), icon: "spark", hash: "#/agentes", routes: ["agentes", "agente"] },
  { id: "agentes-historico", label: t("Histórico de agentes"), icon: "history", hash: "#/agentes/historico" },
  { id: "agentes-branches", label: t("Branches e worktrees"), icon: "tree", hash: "#/agentes/branches" },
  { id: "agentes-uso", label: t("Uso e custo"), icon: "gauge", hash: "#/agentes/uso" },
  { id: "prompts", label: t("Prompts"), icon: "text", hash: "#/prompts" },
];
// Help: sits at the end of the sidebar; the section content goes into the ⌘K search
export const HELP_NAV = [
  { id: "ajuda", label: t("Ajuda"), icon: "help", hash: "#/ajuda" },
];
// stable groups, in fixed order, collapsible (state remembered); the first one and Help, at the end, have no title
export const NAV_GROUPS = [
  { id: "geral", label: "", items: ["inicio", "overview"] },
  { id: "projetos", label: t("Projetos"), items: ["sites", "node", "terminals"] },
  { id: "ambiente", label: t("Ambiente"), items: ["ambiente", "depuracao"] },
  { id: "agentes", label: t("Agentes"), items: ["agentes", "prompts", "agentes-uso", "agentes-branches", "agentes-historico"] },
  { id: "organizar", label: t("Organizar"), items: ["tasks", "notes", "tags", "index"] },
  { id: "ajuda", label: "", items: ["ajuda"] },
];
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
