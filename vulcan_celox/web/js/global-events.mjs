// Global listeners of the shell; split out of app.mjs.

import { onJobsChange } from "./ai.mjs";
import { startNotices } from "./attention-notify.mjs";
import { startPrStatus } from "./pr-status.mjs";
import { startPorts } from "./terminal-ports.mjs";
import { startSidebarPrefs } from "./sidebar-prefs.mjs";
import { startTheme } from "./theme.mjs";
import { clearTab, dismissSession, latestAttention, startAttention } from "./attention-state.mjs";
import { isMac, isNative } from "./api.mjs";
import { app } from "./app-state.mjs";
import { stepTerminalTurn } from "./terminal-watch.mjs";
import { loadNodeProjects, navigate, refreshState, reportDragRegions, route, runCommand, service, toggleAutostart } from "./app.mjs";
import { CurrentSession } from "./current-session.mjs";
import { $, debounce, reportError } from "./dom.mjs";
import { sectionFor } from "./help-content.mjs";
import { palette } from "./palette.mjs";
import { SessionTree } from "./session-tree.mjs";
import { renderSidebar } from "./sidebar.mjs";
import { addSiteDialog } from "./site-add.mjs";
import { TerminalPanel } from "./terminal-panel.mjs";
import { terminals } from "./terminals.mjs";
import { addNodeDialog } from "./views/node.mjs";

export function bindGlobalEvents() {
  window.addEventListener("hashchange", route);
  window.addEventListener("popstate", route);
  window.addEventListener("resize", reportDragRegions);

  document.addEventListener("click", (event) => {
    const go = event.target.closest("[data-go]");
    if (go) navigate(go.dataset.go);
    const svc = event.target.closest("[data-service]");
    if (svc) service(svc.dataset.service);
    if (event.target.closest("#open-palette")) palette.open();
    if (event.target.closest("#help-here")) runCommand("help");  // Help already at the section of the current screen
    if (event.target.closest("#add-node")) {
      addNodeDialog().then((added) => {
        if (!added) return;
        loadNodeProjects();
        navigate(`#/node/${encodeURIComponent(added.name)}`);
      }).catch(reportError);
    }
    if (event.target.closest("#add-site")) {
      addSiteDialog({ backend: app.state ? app.state.backend : null, onDone: () => refreshState() });
    }
    if (event.target.closest("#env [data-action='autostart']")) toggleAutostart();
    if (event.target.id === "palette") palette.close();
    const item = event.target.closest(".pal-item");
    if (item) palette.run(Number(item.dataset.index));
  });

  app.tree = new SessionTree($("#side-sessions"), { navigate, route: () => app.route });
  $("#nav").addEventListener("click", (event) => {
    const head = event.target.closest("[data-nav-group]");
    if (!head) return;
    app.tree.toggle(`nav:${head.dataset.navGroup}-closed`);
    renderSidebar();
  });
  app.current = new CurrentSession($("#current-session"));
  app.panel = new TerminalPanel($("#term-panel"), { sites: () => (app.state ? app.state.sites : []) });
  const sitesToggle = $("[data-side-toggle='section:sites']");
  const applySites = () => {
    const open = app.tree.isOpen("section:sites");
    sitesToggle.setAttribute("aria-expanded", String(open));
    $("#side-sites").classList.toggle("is-collapsed", !open);
  };
  sitesToggle.addEventListener("click", () => {
    app.tree.toggle("section:sites");
    applySites();
  });
  applySites();
  const nodeToggle = $("[data-side-toggle='section:node']");
  const applyNode = () => {
    const open = !app.tree.isOpen("section:node-closed");  // new section: open for those who already had saved preferences
    nodeToggle.setAttribute("aria-expanded", String(open));
    $("#side-node").classList.toggle("is-collapsed", !open);
  };
  nodeToggle.addEventListener("click", () => {
    app.tree.toggle("section:node-closed");
    applyNode();
  });
  applyNode();
  window.addEventListener("vulcan-node-changed", () => loadNodeProjects());
  // tab opened by a project script appears in the bottom panel, without leaving the screen
  window.addEventListener("vulcan-show-terminal", async (event) => {
    const id = event.detail && event.detail.id;
    if (!id) return;
    if (app.panel && app.panel.available) {
      app.panel.toggle(true);
      if (app.panel.ws) app.panel.ws.select(id);
    } else {
      navigate(`#/terminals/terminal/${id}`);
    }
  });
  startTheme();
  startSidebarPrefs();
  startNotices();
  startPorts();
  startPrStatus();
  startAttention();
  const reloadTree = debounce(() => app.tree.load(), 300);
  onJobsChange(() => reloadTree());

  $("#site-filter").addEventListener("input", (e) => {
    app.siteFilter = e.target.value.trim();
    renderSidebar();
  });

  $("#palette-input").addEventListener("input", (e) => palette.search(e.target.value));
  $("#palette-input").addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { palette.index = Math.min(palette.items.length - 1, palette.index + 1); palette.render(); e.preventDefault(); }
    if (e.key === "ArrowUp") { palette.index = Math.max(0, palette.index - 1); palette.render(); e.preventDefault(); }
    if (e.key === "Enter") { palette.run(palette.index); e.preventDefault(); }
    if (e.key === "Escape") palette.close();
  });

  document.addEventListener("keydown", (event) => {
    // macOS: ⌘; Linux: Ctrl+Shift (Ctrl alone belongs to the terminal)
    const mod = isMac ? event.metaKey : event.ctrlKey && event.shiftKey;
    if (!mod) {
      if (event.key === "Escape" && !$("#palette").hidden) palette.close();
      return;
    }
    const digit = /^Digit([1-9])$/.exec(event.code || "");
    const key = digit && !isMac ? digit[1] : event.key.toLowerCase();
    // in the native shell the menus already handle these shortcuts; in the browser we handle them here
    if (key === "k") { event.preventDefault(); palette.open(); }
    if (key === "p" && event.shiftKey) { event.preventDefault(); navigate("#/prompts"); }
    if (key === "j") { event.preventDefault(); runCommand("togglePanel"); }
    if (event.shiftKey && (key === "arrowup" || key === "arrowdown")) {
      event.preventDefault();
      const direction = key === "arrowup" ? -1 : 1;
      const inTerminal = document.activeElement && document.activeElement.closest(".xterm");
      if (inTerminal || !(app.view && app.view.stepTurn && app.view.stepTurn(direction))) stepTerminalTurn(direction);
    }
    if (key === "u" && event.shiftKey) {
      event.preventDefault();
      const latest = latestAttention();
      if (latest && latest.tab) {
        clearTab(latest.tab);
        window.dispatchEvent(new CustomEvent("vulcan-show-terminal", { detail: { id: latest.tab } }));
      } else if (latest) {
        dismissSession(latest.session);
        navigate(`#/agentes/${encodeURIComponent(latest.session)}`);
      }
    }
    // ⌘? opens Help already at the section of the current screen
    if (key === "?" || (key === "/" && event.shiftKey)) { event.preventDefault(); navigate(`#/ajuda/${sectionFor(app.route)}`); }
    if (key === "e" && event.shiftKey) { event.preventDefault(); navigate("#/depuracao"); }  // shortcut for the Depuração screen
    // ⌘F (Ctrl+Shift+F on Linux) searches the terminal when there is one on screen; otherwise normal behavior
    if (key === "f" && (!isMac || !event.shiftKey) && document.querySelector(".term-workspace .tab")) {
      event.preventDefault();
      runCommand("find");
    }
    // on the native app ⌘T comes from the menu; ⇧⌘T has no menu item and arrives here
    if ((!isNative || event.shiftKey) && key === "t") { event.preventDefault(); runCommand(event.shiftKey ? "newTerminalOptions" : "newTerminal"); }
    if (/^[1-9]$/.test(key) && (!isMac || !event.shiftKey) && (app.route.name === "site" || app.route.name === "terminals") && !isNative) {
      event.preventDefault();
      runCommand(`tab:${key}`);
    }
  });

  terminals.subscribe(() => {
    renderSidebar();
    reloadTree();
  });
}
