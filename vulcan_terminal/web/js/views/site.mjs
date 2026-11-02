// Detalhe de um site no estilo Herd e a página Terminais: abas superiores Terminal, Tarefas, Post-its e Tags
// sempre ligadas à sessão de terminal selecionada na barra de sessões.

import { get, isMac, native, patch, post, put } from "../api.mjs";
import { confirmDialog } from "../ai.mjs";
import { copy } from "../agents-ui.mjs";

const NEW_TERMINAL_KEY = isMac ? "⌘T" : "Ctrl+Shift+T";
import { $, esc, icon, progressBar, reportError, toast } from "../dom.mjs";
import { terminals, TerminalWorkspace } from "../terminals.mjs";

const TABS = [
  { id: "terminal", label: "Terminal", icon: "terminal" },
  { id: "tasks", label: "Tarefas", icon: "check-square" },
  { id: "notes", label: "Post-its", icon: "note" },
  { id: "tags", label: "Tags", icon: "tag" },
];

class SessionTabsView {
  get tabList() {
    return TABS;
  }

  /** @param {{tab: string, sessionId?: string, state: object, navigate: Function, onChange: Function}} options */
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.tab = this.tabList.some((t) => t.id === options.tab) ? options.tab : "terminal";
    this.workspace = null;
    this.root.addEventListener("click", (e) => this.onClick(e));
  }

  /** Prefixo da rota, sem aba nem sessão. */
  get base() {
    return "#/terminals";
  }

  tabsHtml() {
    return `
      <div class="segmented seg-tabs" role="tablist" aria-label="Seções da sessão">
        ${this.tabList.map((t) => `<button class="seg ${t.id === this.tab ? "is-on" : ""}" role="tab" aria-selected="${t.id === this.tab}" data-tab="${t.id}">
          ${icon(t.icon)}<span>${t.label}</span><span class="count" data-count="${t.id}"></span></button>`).join("")}
      </div>`;
  }

  mountWorkspace(body, extra) {
    this.workspace = new TerminalWorkspace(body, {
      ...extra,
      mode: this.tab,
      sessionId: this.options.sessionId,
      focus: this.options.focus,
      sites: this.options.state.sites,
      onChange: () => this.updateCounts(),
      onSelect: () => this.syncRoute(),
      onDataChange: () => this.options.onChange(),
    });
    this.updateCounts();
  }

  syncRoute() {
    const id = this.workspace && this.workspace.activeId;
    const hash = `${this.base}/${this.tab}${id ? `/${id}` : ""}`;
    if (location.hash !== hash) this.options.navigate(hash, { replace: true, silent: true });
    this.updateCounts();
  }

  updateCounts() {
    const ws = this.workspace;
    const record = ws ? ws.records.get(ws.activeId) : null;
    const counts = {
      terminal: ws ? ws.sessions().length : 0,
      tasks: record ? record.tasks.total - record.tasks.done : 0,
      notes: record ? record.notes : 0,
      tags: record ? record.tags.length : 0,
    };
    this.root.querySelectorAll("[data-count]").forEach((el) => {
      const value = counts[el.dataset.count];
      el.textContent = value ? String(value) : "";
    });
  }

  setTab(tab) {
    if (!this.tabList.some((t) => t.id === tab)) return;
    this.tab = tab;
    this.root.querySelectorAll("[data-tab]").forEach((b) => {
      const on = b.dataset.tab === tab;
      b.classList.toggle("is-on", on);
      b.setAttribute("aria-selected", String(on));
    });
    if (this.workspace) this.workspace.setMode(tab);
    this.syncRoute();
  }

  onClick(event) {
    const tab = event.target.closest("[data-tab]");
    if (tab && this.root.contains(tab) && !tab.closest(".term-workspace")) {
      this.setTab(tab.dataset.tab);
      return true;
    }
    return false;
  }

  /** Chamado pelo roteador quando só muda a sessão, a aba ou o item em destaque. */
  reveal(route) {
    if (!this.workspace) return;
    const tab = this.tabList.some((t) => t.id === route.tab) ? route.tab : "terminal";
    this.tab = tab;
    this.root.querySelectorAll("[data-tab]").forEach((b) => {
      const on = b.dataset.tab === tab;
      b.classList.toggle("is-on", on);
      b.setAttribute("aria-selected", String(on));
    });
    this.workspace.reveal(route.session || this.workspace.activeId, tab, route.focus);
    this.updateCounts();
  }

  newTerminal(command = null, title = null, options = {}) {
    if (!this.workspace) return null;
    return this.workspace.newTerminal(command, title, options).then((s) => {
      if (s && this.tab !== "terminal") this.setTab("terminal"); // só troca de aba se o terminal abriu
      this.syncRoute();
      return s;
    });
  }

  command(name) {
    if (name === "newTerminal") return this.newTerminal();
    if (name === "newTerminalOptions") return this.newTerminal(null, null, { ask: true });
    if (!this.workspace) return null;
    if (name === "popoutTerminal") return this.workspace.popoutActive() || true;
    if (name === "find") return this.workspace.openSearch() || null;
    if (name.startsWith("tab:")) {
      const id = this.workspace.tabIds()[Number(name.slice(4)) - 1];
      if (id) this.workspace.select(id);
      return true;
    }
    return null;
  }

  destroy() {
    if (this.workspace) this.workspace.destroy();
  }
}

export class SiteView extends SessionTabsView {
  get tabList() {
    return [...TABS, { id: "harness", label: "Harness", icon: "check-square" },  // vt-23 C2: contrato dos agentes
      { id: "logs", label: "Logs", icon: "text" },  // vt-05 C6: laravel.log e logs do Lerd
      ...(this.options.state.backend && this.options.state.backend.name === "lerd" ? [{ id: "debug", label: "Depuração", icon: "bolt" }] : [])];
  }

  /** @param {{site: object, tab: string, sessionId?: string, state: object, navigate: Function, onChange: Function}} options */
  constructor(root, options) {
    super(root, options);
    this.site = options.site;
    this.unsubscribe = terminals.subscribe(() => this.updateCounts());
    this.render();
  }

  get base() {
    return `#/sites/${encodeURIComponent(this.site.name)}`;
  }

  render() {
    const s = this.site;
    const progress = (this.options.state.progress.sites || {})[s.name];
    const [label, ...rest] = s.domain.split(".");
    const tld = rest.length ? `.${rest.join(".")}` : "";
    // vt-02 C3: com Lerd ou Valet, os selos viram botões que mudam PHP, Node e HTTPS
    const live = Boolean(this.options.state.backend && this.options.state.backend.available && s.kind !== "manual");
    const lerd = live && this.options.state.backend.name === "lerd";
    const starred = (this.options.state.favorites || []).includes(s.name);
    const chip = (action, cls, inner, title) => live
      ? `<button type="button" class="badge badge-btn ${cls}" data-action="${action}" title="${esc(title)}">${inner}</button>`
      : `<span class="badge ${cls}" title="${esc(title)}">${inner}</span>`;
    const badges = [
      chip("site-php", "", `PHP ${esc(s.php || "?")}`, live ? "Trocar a versão de PHP do site" : "Versão de PHP"),
      s.node || live ? chip("site-node", "", `Node ${esc(s.node || "?")}`, live ? "Trocar a versão de Node do site" : "Versão de Node") : "",
      chip("site-https", s.secured ? "badge-ok" : "", `${icon(s.secured ? "lock" : "unlock")}${s.secured ? "HTTPS" : "HTTP"}`,
        live ? (s.secured ? "Desligar HTTPS" : "Ligar HTTPS") : (s.secured ? "Servido com HTTPS" : "Sem HTTPS")),
      !s.exists ? `<span class="badge badge-err">${icon("alert")}pasta não encontrada</span>` : "",
    ].join("");
    this.root.innerHTML = `
      <section class="site">
        <header class="site-bar">
          <div class="site-ident" title="${esc(s.path)}">
            <h1 class="site-title">${esc(s.name)}</h1>
            <button class="icon-btn icon-btn-sm site-star ${starred ? "is-on" : ""}" data-action="site-favorite" aria-pressed="${starred}"
              title="${starred ? "Tirar dos favoritos" : "Marcar como favorito"}" aria-label="Favorito">${icon("star")}</button>
            <a class="site-domain" href="${esc(s.url)}" data-action="open-url" title="Abrir ${esc(s.url)}">${esc(label)}<span>${esc(tld)}</span></a>
            <div class="badges">${badges}</div>
          </div>
          ${this.tabsHtml()}
          <div class="site-actions">
            ${progress && progress.total ? `<span class="site-progress" title="Tarefas concluídas no site">${progressBar(progress)}<span class="num dim">${progress.done}/${progress.total}</span></span>` : ""}
            <button class="icon-btn" data-action="open-url" title="Abrir site" aria-label="Abrir site">${icon("globe")}</button>
            <button class="icon-btn" data-action="copy-url" title="Copiar URL" aria-label="Copiar URL">${icon("copy")}</button>
            ${live ? `<button class="icon-btn" data-action="site-share" title="Compartilhar na internet" aria-label="Compartilhar o site">${icon("external")}</button>` : ""}
            ${lerd ? `<button class="icon-btn" data-action="site-db" title="Banco de dados (lerd db:shell)" aria-label="Abrir o banco de dados">${icon("database")}</button>
            <button class="icon-btn" data-action="site-doctor" title="Diagnóstico do site (lerd site:doctor)" aria-label="Diagnóstico do site">${icon("check-square")}</button>
            <button class="icon-btn" data-action="site-dashboard" title="Abrir este site no painel do Lerd" aria-label="Abrir no painel do Lerd">${icon("gauge")}</button>` : ""}
            ${s.has_artisan ? `<button class="icon-btn" data-action="tinker" title="Tinker" aria-label="Abrir Tinker">${icon("bolt")}</button>` : ""}
            <button class="icon-btn" data-action="finder" title="Mostrar no Finder" aria-label="Mostrar no Finder" ${s.exists ? "" : "disabled"}>${icon("folder")}</button>
            <button class="icon-btn" data-action="editor" title="Abrir no editor" aria-label="Abrir no editor" ${s.exists ? "" : "disabled"}>${icon("code")}</button>
            <button class="icon-btn" data-action="site-remove" title="Remover o site" aria-label="Remover o site">${icon("trash")}</button>
            <button class="btn btn-primary" data-action="new-terminal" title="Novo terminal (${NEW_TERMINAL_KEY})" ${s.exists ? "" : "disabled"}>${icon("plus")}<span>Terminal</span></button>
          </div>
        </header>
        <div class="site-body" data-role="body"></div>
      </section>`;
    native({ type: "setTitle", title: `${s.name} · Vulcan Terminal` });
    try {
      localStorage.setItem("vulcan-last-site", s.name);
    } catch {
      /* armazenamento indisponível */
    }
    this.mountWorkspace($("[data-role=body]", this.root), { site: s, scope: "site" });
  }

  async onClick(event) {
    if (super.onClick(event)) return;
    const target = event.target.closest(".site-bar [data-action]");
    if (!target) return;
    const action = target.dataset.action;
    event.preventDefault();
    try {
      if (action === "open-url") await post("/api/open", { kind: "url", target: this.site.url });
      if (action === "finder") await post("/api/open", { kind: "finder", target: this.site.path });
      if (action === "editor") await post("/api/open", { kind: "editor", target: this.site.path });
      if (action === "new-terminal") await this.newTerminal();
      if (action === "tinker") await this.newTerminal("php artisan tinker", `${this.site.name} · tinker`);
      if (action === "site-https") await this.toggleHttps();
      if (action === "site-share") await this.share();
      if (action === "site-remove") await this.remove();
      if (action === "share-copy") await copy(target.dataset.url, `Copiado: ${target.dataset.url}`);
      if (action === "site-favorite") {
        const on = target.getAttribute("aria-pressed") !== "true";
        await put(`${this.siteUrl()}/favorite`, { favorite: on });
        target.classList.toggle("is-on", on);
        target.setAttribute("aria-pressed", String(on));
        if (window.vulcanCommand) window.vulcanCommand("refresh");
      }
      if (action === "copy-url" && await copy(this.site.url, `Copiado: ${this.site.url}`)) target.blur();
      if (action === "site-db" || action === "site-doctor") await this.siteAction(action.slice(5));
      if (action === "site-dashboard") await post(`${this.siteUrl()}/actions/dashboard`);
      if (action === "site-php") await this.changeVersion("php");
      if (action === "site-node") await this.changeVersion("node");
    } catch (err) {
      reportError(err);
    }
  }

  siteUrl() {
    return `/api/sites/${encodeURIComponent(this.site.name)}`;
  }

  /** Remover em três níveis (vt-02 C7): lista ou backend, e opcionalmente a pasta para a Lixeira. */
  async remove() {
    const s = this.site;
    const manual = s.kind === "manual";
    const backend = this.options.state.backend;
    let trash = false;
    let typed = "";
    const yes = await confirmDialog({
      title: `Remover ${s.name}`,
      body: `<p>${manual ? "Tira o site da lista do Vulcan Terminal." : `Desregistra o site do ${esc(backend.label)}: ele deixa de ser servido em <code>${esc(s.domain)}</code>.`}
        A pasta fica onde está.</p>
        <label class="dialog-check"><input type="checkbox" data-trash><span>Também mover a pasta <code>${esc(s.path)}</code> para a Lixeira</span></label>
        <label class="field-label" for="remove-confirm">Para mover para a Lixeira, digite <b>${esc(s.name)}</b></label>
        <input id="remove-confirm" class="input" data-typed spellcheck="false" autocomplete="off">`,
      confirmLabel: "Remover",
      danger: true,
      onDecide: (answer, root) => {
        trash = root.querySelector("[data-trash]").checked;
        typed = root.querySelector("[data-typed]").value.trim();
      },
    });
    if (!yes) return;
    if (trash && typed !== s.name) {
      toast("O nome digitado não confere: nada foi removido.", { kind: "error" });
      return;
    }
    const url = `${this.siteUrl()}/remove`;
    let result;
    try {
      result = await post(url, { level: manual ? "list" : "backend" });
    } catch (err) {
      if (err.status !== 409 || !/parkeado/.test(err.message)) throw err;
      const parent = await confirmDialog({ title: "Site parkeado", body: `<p>${esc(err.message)}.</p>`, confirmLabel: "Esquecer a pasta mãe", danger: true });
      if (!parent) return;
      result = await post(url, { level: "backend", parent: true });
    }
    if (result.ok === false) {
      toast(`O backend recusou: ${(result.output || "").split("\n").pop()}`, { kind: "error", timeout: 8000 });
      return;
    }
    if (trash) {
      if (window.vulcanCommand) window.vulcanCommand("refresh");
      await new Promise((r) => setTimeout(r, 1200));  // o backend precisa parar de listar o site
      const moved = await post("/api/sites/trash", { name: s.name, confirm: typed });
      toast(`Pasta movida para a Lixeira: ${moved.moved_to}`, { kind: "ok", timeout: 6000 });
    } else {
      toast(manual ? "Site tirado da lista." : "Site desregistrado. A pasta continua no lugar.", { kind: "ok" });
    }
    location.hash = "#/overview";
    if (window.vulcanCommand) window.vulcanCommand("refresh");
  }

  async share() {
    const lerd = this.options.state.backend.name === "lerd";
    const tools = [["", "Padrão do Lerd"], ["cloudflare", "Cloudflare Tunnel"], ["ngrok", "ngrok"], ["expose", "Expose"],
      ["localhost-run", "localhost.run (sem conta)"], ["serveo", "serveo.net (sem conta)"], ["pinggy", "Pinggy (sem conta)"]];
    let tool = "";
    const yes = await confirmDialog({
      title: `Compartilhar ${this.site.domain}`,
      body: `<p>O site fica acessível na internet por um túnel enquanto a aba do compartilhamento estiver aberta.
        Fechar a aba encerra o túnel.</p>${lerd ? `<select class="select" data-tool>${tools.map(([id, label]) =>
        `<option value="${id}">${esc(label)}</option>`).join("")}</select>` : ""}`,
      confirmLabel: "Compartilhar",
      onDecide: (answer, root) => { const el = root.querySelector("[data-tool]"); tool = el ? el.value : ""; },
    });
    if (!yes) return;
    const tab = await post(`${this.siteUrl()}/share`, { tool });
    await terminals.sync();
    if (this.workspace) this.workspace.select(tab.id);
    this.watchShare(tab.id);
  }

  /** Procura a URL pública na saída da aba por até 2 min e mostra o chip para copiar enquanto a aba existir. */
  async watchShare(id) {
    const actions = $(".site-actions", this.root);
    for (let i = 0; i < 80 && !this.destroyed; i += 1) {
      await new Promise((r) => setTimeout(r, 1500));
      const live = terminals.get(id);
      if (!live || !live.alive) return;
      let data;
      try {
        data = await get(`/api/terminals/${id}/public-url`);
      } catch {
        return;
      }
      if (data.url && actions) {
        const chip = document.createElement("button");
        chip.className = "share-chip";
        chip.dataset.action = "share-copy";
        chip.dataset.url = data.url;
        chip.title = "Copiar a URL pública";
        chip.innerHTML = `${icon("copy")}<span>${esc(data.url.replace("https://", ""))}</span>`;
        actions.prepend(chip);
        const off = terminals.subscribe(() => {
          const t = terminals.get(id);
          if (!t || !t.alive) { chip.remove(); off(); }
        });
        return;
      }
    }
  }

  async siteAction(name) {
    const tab = await post(`${this.siteUrl()}/actions/${name}`);
    await terminals.sync();
    if (this.workspace) this.workspace.select(tab.id);
  }

  async toggleHttps() {
    const s = this.site;
    const info = await get(`${this.siteUrl()}/versions`);
    const writes = info.writes.secure ? `<p class="dim">O backend vai atualizar ${esc(info.writes.secure)} do projeto.</p>` : "";
    const yes = await confirmDialog({
      title: s.secured ? `Desligar HTTPS em ${s.domain}` : `Ligar HTTPS em ${s.domain}`,
      body: `<p>${s.secured ? "O site volta a ser servido por <code>http://</code> e o certificado sai."
        : "O backend emite um certificado local (mkcert) e passa a servir por <code>https://</code>."}</p>${writes}`,
      confirmLabel: s.secured ? "Desligar HTTPS" : "Ligar HTTPS",
    });
    if (!yes) return;
    const result = await patch(this.siteUrl(), { secured: !s.secured });
    if (result.ok) toast(s.secured ? "HTTPS desligado." : "HTTPS ligado.", { kind: "ok" });
    else toast(`O backend recusou: ${(result.output || "").split("\n").pop()}`, { kind: "error", timeout: 8000 });
    if (window.vulcanCommand) window.vulcanCommand("refresh");
  }

  async changeVersion(kind) {
    const s = this.site;
    const info = await get(`${this.siteUrl()}/versions`);
    const current = info.current[kind] || "";
    const field = kind === "php"
      ? `<select class="select" data-version>${info.php.map((v) => `<option value="${esc(v.version)}" ${v.version === current ? "selected" : ""}>PHP ${esc(v.version)}${v.default ? " (padrão)" : ""}</option>`).join("")}</select>`
      : `<input class="input" data-version value="${esc(current)}" placeholder="22, 20.11 ou lts" spellcheck="false">`;
    const writes = info.writes[kind] ? `<p class="dim">O backend grava ${esc(info.writes[kind])} na pasta do projeto.</p>` : "";
    let chosen = "";
    const yes = await confirmDialog({
      title: kind === "php" ? `Versão de PHP de ${s.name}` : `Versão de Node de ${s.name}`,
      body: `${field}${writes}<p class="dim">O comando roda numa aba deste site; pode demorar se a imagem da versão ainda não existir.</p>`,
      confirmLabel: "Trocar",
      confirmDisabled: kind === "php" && !info.php.length,
      onDecide: (answer, root) => { chosen = root.querySelector("[data-version]").value.trim(); },
    });
    if (!yes || !chosen || chosen === current) return;
    const tab = await patch(this.siteUrl(), { [kind]: chosen });
    await terminals.sync();
    if (this.workspace) this.workspace.select(tab.id);
    if (window.vulcanCommand) setTimeout(() => window.vulcanCommand("refresh"), 1500);
  }

  destroy() {
    this.destroyed = true;
    this.unsubscribe();
    super.destroy();
  }
}

export class TerminalsView extends SessionTabsView {
  constructor(root, options) {
    super(root, options);
    this.unsubscribe = terminals.subscribe(() => this.updateCounts());
    this.root.innerHTML = `
      <section class="site">
        <header class="site-bar">
          <div class="site-ident"><h1 class="site-title">Todas as sessões</h1>
            <span class="dim">terminais de todos os sites e globais</span></div>
          ${this.tabsHtml()}
          <div class="site-actions">
            <button class="btn btn-primary" data-action="new-terminal" title="Novo terminal (${NEW_TERMINAL_KEY})">${icon("plus")}<span>Terminal</span></button>
          </div>
        </header>
        <div class="site-body" data-role="body"></div>
      </section>`;
    this.mountWorkspace($("[data-role=body]", this.root), { site: null, scope: "all" });
  }

  onClick(event) {
    if (super.onClick(event)) return;
    if (event.target.closest(".site-bar [data-action='new-terminal']")) this.newTerminal();
  }

  destroy() {
    this.unsubscribe();
    super.destroy();
  }
}
