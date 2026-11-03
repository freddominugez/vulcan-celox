// Estado da casca e itens da barra lateral.

import { route } from "./app.mjs";
import { icon } from "./dom.mjs";
import { t } from "./i18n.mjs";

export const NAV = [
  { id: "inicio", label: t("Início"), icon: "home", hash: "#/inicio" },
  { id: "overview", label: t("Visão geral"), icon: "grid", hash: "#/overview" },
  // Atalho do grupo Projetos para os sites PHP (a lista fica na seção Sites, separada da de Node)
  { id: "sites", label: t("Sites PHP"), icon: "globe", hash: "#/overview", routes: ["site"] },
  { id: "terminals", label: t("Terminais"), icon: "terminal", hash: "#/terminals" },
  { id: "node", label: t("Projetos Node"), icon: "hex", hash: "#/node", routes: ["node", "node-projeto"] },
  { id: "tasks", label: t("Tarefas"), icon: "check-square", hash: "#/tasks" },
  { id: "notes", label: t("Post-its"), icon: "note", hash: "#/notes" },
  { id: "tags", label: t("Tags"), icon: "tag", hash: "#/tags" },
  { id: "index", label: t("Índice"), icon: "book", hash: "#/index" },
  // O Lerd tem item próprio, com o estado dele; #/ambiente continua valendo
  { id: "ambiente", label: "Lerd", icon: "database", hash: "#/lerd", routes: ["ambiente"] },
  { id: "depuracao", label: t("Depuração"), icon: "bolt", hash: "#/depuracao" },
];
// Painel de agentes: sessões do Claude Code e do Codex lidas do disco
export const AGENT_NAV = [
  { id: "agentes", label: t("Agentes"), icon: "spark", hash: "#/agentes", routes: ["agentes", "agente"] },
  { id: "agentes-historico", label: t("Histórico de agentes"), icon: "history", hash: "#/agentes/historico" },
  { id: "agentes-branches", label: t("Branches e worktrees"), icon: "tree", hash: "#/agentes/branches" },
  { id: "agentes-uso", label: t("Uso e custo"), icon: "gauge", hash: "#/agentes/uso" },
  { id: "prompts", label: t("Prompts"), icon: "text", hash: "#/prompts" },
];
// Ajuda: fica no fim da barra lateral; o conteúdo das seções entra na busca ⌘K
export const HELP_NAV = [
  { id: "ajuda", label: t("Ajuda"), icon: "help", hash: "#/ajuda" },
];
// Grupos estáveis, em ordem fixa, recolhíveis (estado lembrado); o primeiro e a Ajuda, no fim, não têm título
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
