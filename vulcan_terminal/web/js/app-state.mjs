// Estado da casca e itens da barra lateral; separado de app.mjs no vt-32 C2.

import { route } from "./app.mjs";
import { icon } from "./dom.mjs";

export const NAV = [
  { id: "inicio", label: "Início", icon: "home", hash: "#/inicio" },
  { id: "overview", label: "Visão geral", icon: "grid", hash: "#/overview" },
  // vt-27 C4: atalho do grupo Projetos para os sites PHP (a lista fica na seção Sites, separada da de Node)
  { id: "sites", label: "Sites PHP", icon: "globe", hash: "#/overview", routes: ["site"] },
  { id: "terminals", label: "Terminais", icon: "terminal", hash: "#/terminals" },
  { id: "node", label: "Projetos Node", icon: "hex", hash: "#/node", routes: ["node", "node-projeto"] },
  { id: "tasks", label: "Tarefas", icon: "check-square", hash: "#/tasks" },
  { id: "notes", label: "Post-its", icon: "note", hash: "#/notes" },
  { id: "tags", label: "Tags", icon: "tag", hash: "#/tags" },
  { id: "index", label: "Índice", icon: "book", hash: "#/index" },
  // vt-25 C5: o Lerd tem item próprio, com o estado dele; #/ambiente continua valendo
  { id: "ambiente", label: "Lerd", icon: "database", hash: "#/lerd", routes: ["ambiente"] },
  { id: "depuracao", label: "Depuração", icon: "bolt", hash: "#/depuracao" },
];
// Painel de agentes (vt-16): sessões do Claude Code e do Codex lidas do disco
export const AGENT_NAV = [
  { id: "agentes", label: "Agentes", icon: "spark", hash: "#/agentes", routes: ["agentes", "agente"] },
  { id: "agentes-historico", label: "Histórico de agentes", icon: "history", hash: "#/agentes/historico" },
  { id: "agentes-branches", label: "Branches e worktrees", icon: "tree", hash: "#/agentes/branches" },
  { id: "agentes-uso", label: "Uso e custo", icon: "gauge", hash: "#/agentes/uso" },
  { id: "prompts", label: "Prompts", icon: "text", hash: "#/prompts" },
];
// Ajuda (vt-26 C2): fica no fim da barra lateral; o conteúdo das seções entra na busca ⌘K
export const HELP_NAV = [
  { id: "ajuda", label: "Ajuda", icon: "help", hash: "#/ajuda" },
];
// vt-27 C4: grupos estáveis, em ordem fixa, recolhíveis (estado lembrado); o primeiro e a Ajuda, no fim, não têm título
export const NAV_GROUPS = [
  { id: "geral", label: "", items: ["inicio", "overview"] },
  { id: "projetos", label: "Projetos", items: ["sites", "node", "terminals"] },
  { id: "ambiente", label: "Ambiente", items: ["ambiente", "depuracao"] },
  { id: "agentes", label: "Agentes", items: ["agentes", "prompts", "agentes-uso", "agentes-branches", "agentes-historico"] },
  { id: "organizar", label: "Organizar", items: ["tasks", "notes", "tags", "index"] },
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
