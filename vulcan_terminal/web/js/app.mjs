// Shell da interface: roteamento, barra superior e comandos nativos. Estado e barra lateral em app-state.mjs e
// sidebar.mjs; paleta em palette.mjs; montagem das telas em view-mount.mjs; ouvintes em global-events.mjs.

import { api, every, get, isMac, isNative, native, patch, token } from "./api.mjs";
import { $, $$, debounce, esc, icon, reportError, toast } from "./dom.mjs";
import { mountPopout, terminals } from "./terminals.mjs";
import { remountsOnSites } from "./remount.mjs";
import { sectionFor } from "./help-content.mjs";
import { AGENT_NAV, HELP_NAV, NAV, app } from "./app-state.mjs";
import { renderSidebar } from "./sidebar.mjs";
import { palette } from "./palette.mjs";
import { bindGlobalEvents } from "./global-events.mjs";
import { mountView } from "./view-mount.mjs";


// ── roteamento ──────────────────────────────────────────────────────────────
function parseRoute(hash) {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  if (parts[0] === "sites" && parts[1]) {
    return { name: "site", site: parts[1], tab: parts[2] || "terminal", session: parts[3] || null, focus: parts[4] || null };
  }
  if (parts[0] === "terminals") return { name: "terminals", tab: parts[1] || "terminal", session: parts[2] || null, focus: parts[3] || null };
  if (parts[0] === "popout" && parts[1]) return { name: "popout", id: parts[1] };
  if (parts[0] === "prompts") return { name: "prompts" };
  if (parts[0] === "lerd") return { name: "ambiente" };
  if (parts[0] === "ajuda") return { name: "ajuda", section: parts[1] || null };
  if (parts[0] === "node") return parts[1] ? { name: "node-projeto", project: parts[1] } : { name: "node" };
  if (parts[0] === "agentes") {
    if (parts[1] === "historico") return { name: "agentes-historico" };
    if (parts[1] === "branches") return { name: "agentes-branches" };
    // #/agentes/uso/AAAA-MM-DD fixa o fim do período (snapshot com fixtures datadas)
    if (parts[1] === "uso") return { name: "agentes-uso", until: /^\d{4}-\d{2}-\d{2}$/.test(parts[2] || "") ? parts[2] : null };
    return parts[1] ? { name: "agente", id: parts[1], tab: parts[2] || null, path: parts[3] || null, line: Number(parts[4]) || null, seq: /^t\d+$/.test(parts[4] || "") ? Number(parts[4].slice(1)) : null } : { name: "agentes" };
  }
  if (NAV.some((n) => n.id === parts[0])) return { name: parts[0] };
  return { name: "overview" };
}

export function navigate(hash, { replace = false, silent = false } = {}) {
  if (silent) {
    history.replaceState(null, "", hash);
    app.route = parseRoute(hash);
    renderSidebar();
    return;
  }
  if (replace) history.replaceState(null, "", hash);
  else if (location.hash !== hash) history.pushState(null, "", hash);
  route();
}

export function route() {
  const previous = app.route;
  app.route = parseRoute(location.hash);
  if (app.route.name === "popout") return;
  // mesma tela de sessões: só troca sessão, aba ou item, sem remontar terminais
  const same = app.view && app.view.reveal && previous.name === app.route.name
    && (app.route.name !== "site" || previous.site === app.route.site);
  if (same) {
    app.view.reveal(app.route);
    renderSidebar();
    renderToolbar();
    return;
  }
  mountView();
  renderSidebar();
  renderToolbar();
  if (app.panel) app.panel.setRoute(app.route.name);
}

function viewTitle() {
  const r = app.route;
  if (r.name === "site") return r.site;
  if (r.name === "agente") return "Sessão de agente";
  if (r.name === "node-projeto") return r.project;
  const nav = [...NAV, ...AGENT_NAV, ...HELP_NAV].find((n) => n.id === r.name);
  if (nav && nav.id === "ambiente" && app.state && app.state.backend.available) return app.state.backend.label;
  return nav ? nav.label : "Vulcan Celox";
}

// ── estado ──────────────────────────────────────────────────────────────────
export async function loadNodeProjects(draw = true) {
  try {
    app.nodeProjects = (await get("/api/node-projects")).projects;
  } catch {
    /* lista de projetos Node é secundária: mantém a última */
  }
  if (draw && app.state) renderSidebar();
}

export async function refreshState() {
  try {
    const previous = app.state;
    app.state = await get("/api/state");
    await loadNodeProjects(false);
    if (app.current) app.current.refresh();
    const sitesChanged = !previous || JSON.stringify(previous.sites) !== JSON.stringify(app.state.sites);
    reportAutostart(app.state.autostart);
    if (app.tree) app.tree.load();
    if (!previous) {
      renderSidebar();
      renderToolbar();
      $("#app").classList.remove("is-offline");
      return;
    }
    if (sitesChanged && remountsOnSites(app.route.name)) {
      mountView();
    } else if (app.view && app.view.update) {
      app.view.update(app.state);
    }
    renderSidebar();
    renderToolbar();
    $("#app").classList.remove("is-offline");
  } catch (err) {
    $("#app").classList.add("is-offline");
    if (err.status === 401) toast("Sessão inválida: abra o app pelo Vulcan Celox.", { kind: "error", timeout: 10000 });
  }
}

// ── início automático do ambiente ───────────────────────────────────────────
function reportAutostart(auto) {
  if (!auto) return;
  const before = app.autostartPhase;
  app.autostartPhase = auto.phase;
  if (before === auto.phase) return;
  if (auto.phase === "starting") toast(`${auto.message[0].toUpperCase()}${auto.message.slice(1)} junto com o app…`, { timeout: 60000 });
  // só avisa o fim de um início que esta janela viu acontecer
  if (before && ["starting", "checking"].includes(before) && auto.phase === "ready" && !/já estava/.test(auto.message)) {
    toast(`${auto.message[0].toUpperCase()}${auto.message.slice(1)}.`, { kind: "ok", timeout: 5000 });
  }
  if (auto.phase === "failed") {
    toast(`${auto.message[0].toUpperCase()}${auto.message.slice(1)}`, {
      kind: "error", timeout: 15000, action: { label: "Tentar de novo", run: () => service("start") },
    });
  }
}

export async function toggleAutostart() {
  const enabled = !(app.state && app.state.autostart && app.state.autostart.enabled);
  try {
    const data = await patch("/api/preferences", { autostart_env: enabled });
    if (app.state) app.state.autostart = data.autostart;
    const label = app.state ? app.state.backend.label : "ambiente";
    toast(enabled ? `O ${label} vai iniciar junto com o Vulcan Celox.` : `O ${label} não inicia mais sozinho.`, { kind: "ok" });
    renderToolbar();
  } catch (err) {
    reportError(err);
  }
}

// ── versão instalada mais nova que a aberta ────────────────────────────────
let outdatedWarned = false;
async function checkBuild() {
  if (outdatedWarned) return;
  try {
    const build = await get("/api/app/build");
    if (!build.outdated) return;
    outdatedWarned = true;
    toast("Uma versão nova do Vulcan Celox foi instalada. Reabra o app para usar (os terminais abertos serão fechados).", {
      timeout: 600000,
      action: isNative ? { label: "Reabrir agora", run: () => native({ type: "relaunch" }) } : null,
    });
  } catch {
    /* sem resposta: tenta de novo no próximo ciclo */
  }
}

// ── barra lateral ───────────────────────────────────────────────────────────

// ── barra superior ──────────────────────────────────────────────────────────
function renderToolbar() {
  const state = app.state;
  $("#crumb").textContent = viewTitle();
  if (!state) return;
  const d = state.status.details || {};
  const running = state.status.running;
  const auto = state.autostart || {};
  const starting = auto.phase === "starting" || auto.phase === "checking";
  const pieces = starting ? [auto.phase === "starting" ? "iniciando…" : "verificando…"] : state.backend.name === "lerd"
    ? [`nginx ${d.nginx ? "ok" : "parado"}`, d.tld ? `.${d.tld} ${d.dns_ok ? "ok" : "falhou"}` : null, d.php_default ? `PHP ${d.php_default}` : null]
    : [state.status.summary];
  $("#env").innerHTML = `
    <span class="env-pill ${running ? "is-ok" : "is-off"}" title="${esc(state.status.summary)}">
      <span class="dot ${running ? "dot-ok" : starting ? "dot-idle" : "dot-err"} ${app.busyService || starting ? "is-busy" : ""}"></span>
      <span class="env-name">${esc(state.backend.label)}</span>
      ${pieces.filter(Boolean).map((p) => `<span class="env-piece">${esc(p)}</span>`).join("")}
    </span>
    <div class="btn-group" role="group" aria-label="Controle do ambiente">
      <button class="icon-btn" data-service="start" title="Iniciar ambiente" aria-label="Iniciar ambiente" ${state.backend.available && !app.busyService && !starting ? "" : "disabled"}>${icon("play")}</button>
      <button class="icon-btn" data-service="stop" title="Parar ambiente" aria-label="Parar ambiente" ${state.backend.available && !app.busyService ? "" : "disabled"}>${icon("stop")}</button>
      <button class="icon-btn" data-service="restart" title="Reiniciar ambiente" aria-label="Reiniciar ambiente" ${state.backend.available && !app.busyService ? "" : "disabled"}>${icon("restart")}</button>
      <button class="icon-btn ${auto.enabled ? "is-on" : ""}" data-action="autostart" aria-pressed="${Boolean(auto.enabled)}"
        title="Iniciar o ${esc(state.backend.label)} junto com o Vulcan Celox: ${auto.enabled ? "ligado" : "desligado"}"
        aria-label="Iniciar o ${esc(state.backend.label)} junto com o app" ${state.backend.available ? "" : "disabled"}>${icon("bolt")}</button>
    </div>`;
  reportDragRegions();
}

export async function service(action) {
  const labels = { start: "Iniciando", stop: "Parando", restart: "Reiniciando" };
  app.busyService = true;
  renderToolbar();
  toast(`${labels[action]} o ambiente… pode levar até um minuto.`, { timeout: 60000 });
  try {
    // lerd start pode baixar imagens e subir a VM do Podman (até 300 s no servidor)
    const result = await api(`/api/services/${action}`, { method: "POST", body: {}, timeout: 330000 });
    toast(result.ok ? "Ambiente atualizado." : `Falhou: ${result.output.split("\n").pop() || "sem detalhes"}`,
      { kind: result.ok ? "ok" : "error", timeout: 6000 });
  } catch (err) {
    reportError(err);
  } finally {
    app.busyService = false;
    refreshState();
  }
}

// ── paleta de comandos ──────────────────────────────────────────────────────

// ── comandos (menus nativos e atalhos) ──────────────────────────────────────
function currentSite() {
  return app.route.name === "site" && app.state ? app.state.sites.find((s) => s.name === app.route.site) : null;
}

export async function runCommand(name) {
  if (name === "palette") return palette.open();
  if (name === "refresh") return setTimeout(refreshState, 800);
  if (name === "help") return navigate(`#/ajuda/${sectionFor(app.route)}`);
  if (name.startsWith("go:")) return navigate(`#/${name.slice(3)}`);
  if (app.view && app.view.command) {
    const handled = app.view.command(name);
    if (handled !== null && handled !== undefined) return handled;
    if (name.startsWith("tab:") || name === "popoutTerminal") return null;
  }
  // nas telas sem terminal o terminal novo abre no painel inferior, sem trocar de tela
  if ((name === "newTerminal" || name === "newTerminalOptions") && app.panel && app.panel.available) {
    return app.panel.newTerminal(name === "newTerminalOptions" ? { ask: true } : {});
  }
  if (name === "togglePanel") return app.panel && app.panel.available ? app.panel.toggle() : null;
  if (name === "find" && app.panel && app.panel.available) return app.panel.find() || null;
  if (name === "newTerminal" || name === "newTerminalOptions") {
    const site = currentSite();
    navigate(site ? `#/sites/${encodeURIComponent(site.name)}/terminal` : "#/terminals/terminal");
    return app.view && app.view.command ? app.view.command(name) : null;
  }
  return null;
}
window.vulcanCommand = runCommand;

// ── área de arrastar da janela nativa ───────────────────────────────────────
export const reportDragRegions = debounce(() => {
  if (!isNative) return;
  const rect = (el) => {
    const r = el.getBoundingClientRect();
    return { x: r.left, y: r.top, w: r.width, h: r.height };
  };
  const drag = $$("[data-drag]").map(rect);
  const noDrag = $$("[data-drag] :is(button, a, input, select, label, [data-nodrag])").map(rect);
  native({ type: "dragRegions", drag, noDrag });
}, 60);

// ── inicialização ───────────────────────────────────────────────────────────

async function initialRoute(state) {
  // O Início abre o app até os quatro passos estarem feitos ou o usuário pular o guia
  try {
    if ((await get("/api/guide")).show_on_open) return "#/inicio";
  } catch {
    /* sem guia: segue a regra antiga */
  }
  let last = null;
  try {
    last = localStorage.getItem("vulcan-last-site");
  } catch {
    last = null;
  }
  const site = state.sites.find((s) => s.name === last) || state.sites[0];
  return site ? `#/sites/${encodeURIComponent(site.name)}/terminal` : "#/overview";
}

function boot() {
  const r = parseRoute(location.hash);
  if (r.name === "popout") {
    document.body.classList.add("is-popout");
    $("#app").hidden = true;
    const root = document.createElement("div");
    root.id = "popout-root";
    document.body.prepend(root);
    mountPopout(root, r.id);
    return;
  }
  if (!token) {
    $("#view").innerHTML = `<div class="page"><div class="empty-block"><h3>Abra pelo app Vulcan Celox</h3>
      <p>Esta interface precisa do token de sessão que o app nativo fornece.</p></div></div>`;
    return;
  }
  if (!isNative) document.body.classList.add("is-browser");
  if (!isMac) $$("kbd[data-mac-shortcut]").forEach((kbd) => { kbd.textContent = kbd.textContent.replace("⌘", "Ctrl+⇧+"); });
  bindGlobalEvents();
  const explicit = Boolean(location.hash && location.hash !== "#" && location.hash !== "#/");
  terminals.sync().catch(reportError);
  refreshState().then(async () => {
    if (!explicit && app.state) navigate(await initialRoute(app.state), { replace: true });
    else route();
  });
  every(5000, refreshState);  // encadeado e pausado com a janela oculta
  every(60000, checkBuild);
  setTimeout(checkBuild, 8000);
  new ResizeObserver(reportDragRegions).observe(document.body);
}

boot();
