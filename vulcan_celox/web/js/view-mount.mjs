// Mounts the screen of the current route; split out of app.mjs.

import { app } from "./app-state.mjs";
import { navigate, refreshState, runCommand } from "./app.mjs";
import { $, esc } from "./dom.mjs";
import { t } from "./i18n.mjs";
import { AgentSessionView } from "./views/agent-session.mjs";
import { AgentsBranchesView } from "./views/agents-branches.mjs";
import { AgentsHistoryView } from "./views/agents-history.mjs";
import { AgentsUsageView } from "./views/agents-usage.mjs";
import { AgentsView } from "./views/agents.mjs";
import { DebugView } from "./views/debug.mjs";
import { EnvironmentView } from "./views/environment.mjs";
import { HelpView } from "./views/help.mjs";
import { HomeView } from "./views/home.mjs";
import { IndexView } from "./views/index.mjs";
import { NodeListView, NodeProjectView } from "./views/node.mjs";
import { NotesView } from "./views/notes.mjs";
import { OverviewView } from "./views/overview.mjs";
import { PromptsView } from "./views/prompts.mjs";
import { SiteView, TerminalsView } from "./views/site.mjs";
import { TagsView } from "./views/tags.mjs";
import { TasksView } from "./views/tasks.mjs";

export function mountView() {
  if (app.view && app.view.destroy) app.view.destroy();
  app.view = null;
  // new element per screen: click listeners from the previous screen must not stay active
  const old = $("#view");
  const root = old.cloneNode(false);
  old.replaceWith(root);
  root.className = `view view-${app.route.name}`;
  const state = app.state;
  const onChange = () => refreshState();
  const common = { state, navigate, onChange, command: runCommand };
  if (!state) {
    root.innerHTML = `<div class="loading"><span class="skeleton w-40"></span><span class="skeleton w-70"></span><span class="skeleton w-55"></span></div>`;
    return;
  }
  switch (app.route.name) {
    case "site": {
      const site = state.sites.find((s) => s.name === app.route.site);
      if (!site) {
        root.innerHTML = `<div class="page"><div class="empty-block"><h3>${t("Site “{site}” não encontrado", { site: esc(app.route.site) })}</h3>
          <p>${t("Ele pode ter sido removido do Lerd. Volte para a visão geral.")}</p>
          <button class="btn" data-go="#/overview">${t("Visão geral")}</button></div></div>`;
        return;
      }
      app.view = new SiteView(root, { ...common, site, tab: app.route.tab, sessionId: app.route.session, focus: app.route.focus });
      break;
    }
    case "terminals":
      app.view = new TerminalsView(root, { ...common, tab: app.route.tab, sessionId: app.route.session, focus: app.route.focus });
      break;
    case "tasks":
      root.innerHTML = `<div class="page page-flush"></div>`;
      app.view = new TasksView(root.firstElementChild, { site: "*", sites: state.sites, onChange });
      break;
    case "notes":
      root.innerHTML = `<div class="page page-flush"><p class="page-note">${t("Post-its globais, fora de projeto. Os de cada site ficam na aba Post-its do site.")}</p><div></div></div>`;
      app.view = new NotesView(root.firstElementChild.lastElementChild, { site: null, onChange });
      break;
    case "tags":
      app.view = new TagsView(root, { onChange });
      break;
    case "index":
      app.view = new IndexView(root, { navigate });
      break;
    case "agentes":
      app.view = new AgentsView(root, { navigate });
      break;
    case "agente":
      app.view = new AgentSessionView(root, { navigate, id: app.route.id, tab: app.route.tab, target: app.route.path ? { path: app.route.path, line: app.route.line, seq: app.route.seq } : null });
      break;
    case "agentes-historico":
      app.view = new AgentsHistoryView(root, { navigate });
      break;
    case "agentes-branches":
      app.view = new AgentsBranchesView(root, { navigate });
      break;
    case "agentes-uso":
      app.view = new AgentsUsageView(root, { navigate, until: app.route.until });
      break;
    case "ajuda":
      app.view = new HelpView(root, { navigate, section: app.route.section });
      break;
    case "inicio":
      app.view = new HomeView(root, { navigate });
      break;
    case "node":
      app.view = new NodeListView(root, { navigate });
      break;
    case "node-projeto":
      app.view = new NodeProjectView(root, { navigate, name: app.route.project });
      break;
    case "prompts":
      app.view = new PromptsView(root, { navigate });
      break;
    case "ambiente":
      app.view = new EnvironmentView(root, { navigate });
      break;
    case "depuracao":
      app.view = new DebugView(root, { sites: state.sites });
      break;
    default:
      app.view = new OverviewView(root, common);
  }
}
