// Tela Ambiente: o que o Lerd mantém rodando, com as ações do dia a dia; o resto fica no painel do Lerd.

import { every, get, post } from "../api.mjs";
import { esc, icon, reportError, toast } from "../dom.mjs";
import { terminals } from "../terminals.mjs";
import { confirmDialog } from "../ai.mjs";
import { t } from "../i18n.mjs";

const REFRESH_MS = 15000;

export class EnvironmentView {
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.data = null;
    this.busy = new Set();
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.root.innerHTML = `<div class="loading"><span class="skeleton w-40"></span><span class="skeleton w-70"></span></div>`;
    this.stopTimer = every(REFRESH_MS, () => this.load());
    this.load();
  }

  async load() {
    try {
      this.data = await get("/api/environment");
      if (this.data.available && this.data.backend === "lerd") {
        [this.php, this.node, this.xdebug] = await Promise.all([get("/api/environment/php").catch(() => null),
          get("/api/environment/node").catch(() => null), get("/api/environment/xdebug").catch(() => null)]);
      }
      this.render();
    } catch (err) {
      reportError(err);
    }
  }

  render() {
    const d = this.data;
    if (!d.available || d.backend !== "lerd") {
      this.root.innerHTML = `<div class="page"><div class="empty-block"><h3>${d.available ? t("{label} não tem esta tela", { label: esc(d.label) }) : t("Sem Lerd ou Valet")}</h3>
        <p>${t("Esta tela mostra o que o Lerd mantém rodando.")} ${d.available ? t("Com o Valet, use os comandos dele no terminal.") : t("Instale o Lerd para ver serviços, PHP e Node aqui.")}</p></div></div>`;
      return;
    }
    this.root.innerHTML = `<div class="page env-page">
      <div class="env-head"><h1>Lerd</h1><span class="dim">${esc(d.label)} · ${t("PHP, nginx, banco e HTTPS dos sites locais")}</span><span class="spacer"></span>
        <button class="btn btn-sm" data-service="start">${icon("play")}<span>${t("Ligar")}</span></button>
        <button class="btn btn-sm" data-service="stop">${icon("stop")}<span>${t("Parar")}</span></button>
        <button class="btn btn-sm" data-action="dashboard">${icon("gauge")}<span>${t("Painel do Lerd")}</span></button></div>
      ${this.servicesHtml()}
      ${this.phpHtml()}
      ${this.nodeHtml()}
    </div>`;
  }

  servicesHtml() {
    const d = this.data;
    const comp = d.components.map((c) => `<li class="env-row">
        <span class="dot ${c.ok ? "dot-ok" : "dot-err"}"></span><span class="env-name">${esc(c.label)}</span>
        ${c.default ? `<span class="badge">${t("padrão")}</span>` : ""}${c.xdebug ? `<span class="badge">Xdebug</span>` : ""}
        <span class="dim env-state">${c.ok ? t("rodando") : t("parado")}</span></li>`).join("");
    const svc = d.services.map((s) => {
      const busy = this.busy.has(s.name);
      return `<li class="env-row">
        <span class="dot ${s.active ? "dot-ok" : "dot-idle"}"></span><span class="env-name">${esc(s.name)}</span>
        ${s.version ? `<span class="badge">${esc(s.version)}</span>` : ""}${s.pinned ? `<span class="badge" title="${t("Nunca parado sozinho")}">${t("fixo")}</span>` : ""}
        ${s.sites ? `<span class="dim">${s.sites > 1 ? t("{n} sites", { n: s.sites }) : t("1 site")}</span>` : ""}
        <span class="dim env-state">${busy ? t("aguarde…") : s.active ? t("rodando") : t("parado")}</span>
        <span class="env-actions">
          <button class="icon-btn icon-btn-sm" data-svc="${esc(s.name)}" data-op="start" title="${t("Iniciar")}" aria-label="${t("Iniciar {name}", { name: esc(s.name) })}" ${busy || s.active ? "disabled" : ""}>${icon("play")}</button>
          <button class="icon-btn icon-btn-sm" data-svc="${esc(s.name)}" data-op="stop" title="${t("Parar")}" aria-label="${t("Parar {name}", { name: esc(s.name) })}" ${busy || !s.active ? "disabled" : ""}>${icon("stop")}</button>
          <button class="icon-btn icon-btn-sm" data-svc="${esc(s.name)}" data-op="restart" title="${t("Reiniciar")}" aria-label="${t("Reiniciar {name}", { name: esc(s.name) })}" ${busy ? "disabled" : ""}>${icon("restart")}</button>
        </span></li>`;
    }).join("");
    return `<section class="panel env-panel">
      <header class="panel-head"><h2>${t("Serviços")}</h2></header>
      <ul class="env-list">${comp}</ul>
      ${d.services.length ? `<div class="env-sub">${t("Serviços instalados")}</div><ul class="env-list">${svc}</ul>`
        : `<p class="env-note dim">${t("Nenhum serviço instalado (mysql, postgres, redis, mailpit...). Instale pelo painel do Lerd ou com <code>lerd service start &lt;nome&gt;</code>.")}</p>`}
    </section>`;
  }

  phpHtml() {
    if (!this.php) return "";
    const fpm = Object.fromEntries(this.data.components.filter((c) => c.id.startsWith("php-")).map((c) => [c.id.slice(4), c]));
    const xd = Object.fromEntries(((this.xdebug && this.xdebug.versions) || []).map((x) => [x.version, x]));
    const rows = this.php.installed.map((v) => {
      const c = fpm[v.version] || {};
      const x = xd[v.version] || { enabled: Boolean(c.xdebug), mode: "" };
      return `<li class="env-row">
        <span class="dot ${c.ok ? "dot-ok" : "dot-idle"}"></span><span class="env-name">PHP ${esc(v.version)}</span>
        ${c.label ? `<span class="dim">${esc(c.label.replace("PHP-FPM ", ""))}</span>` : ""}
        ${v.default ? `<span class="badge badge-ok">${t("padrão")}</span>` : ""}
        ${x.enabled ? `<span class="badge badge-warn" title="${t("O editor precisa escutar na porta {port}", { port: this.xdebugPort() })}">Xdebug ${esc(x.mode || t("ligado"))}${x.on_demand ? t(" · sob demanda") : ""}</span>` : ""}
        <span class="env-actions env-actions-text">
          <button class="btn btn-sm" data-xdebug="${esc(v.version)}" data-on="${x.enabled ? "1" : ""}" title="lerd xdebug ${x.enabled ? "off" : "on"} ${esc(v.version)}">${x.enabled ? t("Desligar Xdebug") : "Xdebug"}</button>
          ${v.default ? "" : `<button class="btn btn-sm" data-php="${esc(v.version)}" data-op="use">${t("Tornar padrão")}</button>`}
          <button class="btn btn-sm" data-ext="${esc(v.version)}" title="${t("Extensões carregadas nesta versão")}">${t("Extensões")}</button>
          <button class="btn btn-sm" data-ini="${esc(v.version)}" title="${t("Os ajustes comuns do php.ini desta versão")}">php.ini</button>
          <button class="btn btn-sm" data-php="${esc(v.version)}" data-op="update" title="lerd php:update ${esc(v.version)}">${t("Atualizar")}</button>
        </span></li>`;
    }).join("");
    const install = this.php.installable.length ? `<div class="env-install">
        <select class="select" data-install>${this.php.installable.map((v) => `<option>${esc(v)}</option>`).join("")}</select>
        <button class="btn btn-sm" data-action="install-php">${icon("plus")}<span>${t("Instalar")}</span></button>
        <span class="dim">${t("Constrói a imagem da versão (<code>lerd fetch</code>) numa aba do terminal.")}</span></div>` : "";
    return `<section class="panel env-panel">
      <header class="panel-head"><h2>PHP</h2><span class="spacer"></span>
        <button class="btn btn-sm" data-ini="shared" title="${t("Ajustes que valem para todas as versões; o de uma versão vence")}">${t("php.ini de todas as versões")}</button></header>
      <ul class="env-list">${rows}</ul>${install}
    </section>`;
  }

  xdebugPort() {
    return (this.xdebug && this.xdebug.port) || 9003;
  }

  /** Liga com modo e sob demanda, ou desliga; reconstrói a imagem do PHP-FPM numa aba do terminal. */
  async xdebugAction(version, isOn) {
    let choice = null;
    const port = this.xdebugPort();
    const yes = await confirmDialog(isOn ? {
      title: t("Desligar o Xdebug do PHP {version}", { version }),
      body: `<p>${t("O Lerd reconstrói a imagem do PHP-FPM desta versão numa aba do terminal; os sites dela param por alguns segundos.")}</p>`,
      confirmLabel: t("Desligar"),
    } : {
      title: t("Xdebug no PHP {version}", { version }),
      body: `<label class="field-label" for="xd-mode">${t("Modo")}</label>
        <select id="xd-mode" class="select" data-xd-mode>
          <option value="debug">${t("debug (passo a passo no editor)")}</option>
          <option value="coverage">${t("coverage (cobertura de testes)")}</option>
          <option value="debug,coverage">${t("debug e coverage")}</option></select>
        <label class="dialog-check"><input type="checkbox" data-xd-demand><span>${t("Sob demanda: só conecta com o cookie ou gatilho de depuração")}</span></label>
        <p class="dim">${t("O editor precisa escutar na porta <b>{port}</b>.", { port })} ${t("O Lerd reconstrói a imagem do PHP-FPM numa aba do terminal.")}</p>`,
      confirmLabel: t("Ligar Xdebug"),
      onDecide: (answer, root) => {
        choice = { mode: root.querySelector("[data-xd-mode]").value, on_demand: root.querySelector("[data-xd-demand]").checked };
      },
    });
    if (!yes) return;
    const result = await post(`/api/environment/php/${encodeURIComponent(version)}/xdebug`,
      isOn ? { enabled: false } : { enabled: true, ...choice });
    await terminals.sync();
    this.options.navigate(`#/terminals/terminal/${result.id}`);
  }

  nodeHtml() {
    const n = this.node;
    if (!n) return "";
    const versions = [...new Set([...n.installed, ...(n.default ? [n.default] : [])])];
    const rows = versions.map((v) => {
      const isDefault = v === n.default;
      const installed = n.installed.includes(v);
      return `<li class="env-row">
        <span class="dot ${installed ? "dot-ok" : "dot-idle"}"></span><span class="env-name">Node ${esc(v)}</span>
        ${isDefault ? `<span class="badge badge-ok">${t("padrão")}</span>` : ""}${installed ? "" : `<span class="dim">${t("não instalada")}</span>`}
        <span class="env-actions env-actions-text">
          ${isDefault || !installed ? "" : `<button class="btn btn-sm" data-node="${esc(v)}" data-op="use">${t("Tornar padrão")}</button>`}
          ${installed && !isDefault ? `<button class="btn btn-sm" data-node="${esc(v)}" data-op="remove">${t("Remover")}</button>` : ""}
        </span></li>`;
    }).join("");
    return `<section class="panel env-panel">
      <header class="panel-head"><h2>Node</h2><span class="dim">${n.manager ? t("gerenciado pelo {manager}", { manager: esc(n.manager) }) : ""}</span></header>
      <ul class="env-list">${rows}</ul>
      <div class="env-install"><input class="input env-node-input" data-node-new placeholder="${t("22, 20.11 ou lts")}" spellcheck="false" aria-label="${t("Versão de Node")}">
        <button class="btn btn-sm" data-action="install-node">${icon("plus")}<span>${t("Instalar")}</span></button>
        <span class="dim">${t("Por site, a versão fica no cabeçalho do site.")}</span></div>
    </section>`;
  }

  async nodeAction(version, op) {
    if (op === "remove") {
      const yes = await confirmDialog({ title: t("Remover o Node {version}", { version }), body: `<p>${t("Projetos fixados nesta versão deixam de achá-la.")}</p>`,
        confirmLabel: t("Remover"), danger: true });
      if (!yes) return;
    }
    const result = await post(`/api/environment/node/${encodeURIComponent(version)}/${op}`, op === "remove" ? { confirm: true } : {});
    if (result.id) {
      await terminals.sync();
      this.options.navigate(`#/terminals/terminal/${result.id}`);
      return;
    }
    if (result.ok) toast(op === "use" ? t("Node {version} agora é o padrão.", { version }) : t("Node {version} removido.", { version }), { kind: "ok" });
    else toast(t("Node {version}: {msg}", { version, msg: (result.output || "").split("\n").pop() }), { kind: "error", timeout: 8000 });
    await this.load();
  }

  /** Seis ajustes comuns, gravados pelo próprio lerd php:ini (o Lerd reaplica o PHP-FPM). */
  async editIni(version) {
    const info = await get(`/api/environment/php/${version}/ini`);
    const hints = { memory_limit: "512M", upload_max_filesize: "64M", post_max_size: "64M", max_execution_time: "60",
      display_errors: "On", error_reporting: "E_ALL" };
    let values = null;
    let open = false;
    const pending = confirmDialog({
      title: version === "shared" ? t("php.ini de todas as versões") : t("php.ini do PHP {version}", { version }),
      body: `<div class="ini-grid">${info.keys.map((k) => `<label class="field-label" for="ini-${k}">${k}</label>
          <input id="ini-${k}" class="input" data-key="${k}" value="${esc(info.values[k] || "")}" placeholder="${esc(hints[k] || "")}" spellcheck="false">`).join("")}</div>
        <p class="dim">${t("Campo vazio volta ao padrão.")} ${version === "shared" ? t("O ajuste de uma versão vence este.") : t("O Lerd guarda uma cópia do arquivo antes e reaplica o PHP-FPM.")}
          ${t("Arquivo:")} <code>${esc(info.path)}</code></p>
        <button type="button" class="btn btn-sm" data-open-ini>${t("Abrir no editor")}</button>`,
      confirmLabel: t("Gravar"),
      onDecide: (answer, root) => {
        values = Object.fromEntries([...root.querySelectorAll("[data-key]")].map((i) => [i.dataset.key, i.value.trim()]));
      },
    });
    // a janela fica no body: o botão é ligado aqui; abrir no editor fecha a janela sem gravar
    const dialogs = document.querySelectorAll(".dialog-backdrop [data-open-ini]");
    const openBtn = dialogs[dialogs.length - 1];
    if (openBtn) {
      openBtn.addEventListener("click", () => {
        open = true;
        openBtn.closest(".dialog").querySelector("[data-answer=no]").click();
      });
    }
    const yes = await pending;
    if (open) {
      await this.openIni(version);
      return;
    }
    const before = info.values;
    if (!yes) return;
    const changes = Object.fromEntries(Object.entries(values).filter(([k, v]) => v !== (before[k] || "")));
    if (!Object.keys(changes).length) return;
    const result = await post(`/api/environment/php/${version}/ini`, { values: changes });
    if (result.ok) toast(t("php.ini gravado e PHP-FPM reaplicado."), { kind: "ok" });
    else toast(t("php.ini: {msg}", { msg: (result.output || "").split("\n").pop() }), { kind: "error", timeout: 8000 });
  }

  /** Extensões carregadas (php -m no contêiner da versão), só leitura; gerenciar fica no painel do Lerd. */
  async showExtensions(version) {
    const info = await get(`/api/environment/php/${version}/extensions`);
    const chips = (list) => list.map((m) => `<span class="chip ext-chip" data-name="${esc(m.toLowerCase())}">${esc(m)}</span>`).join("");
    const pending = confirmDialog({
      title: t("Extensões do PHP {version}", { version }),
      body: `<input class="input" data-ext-search placeholder="${t("Buscar extensão")}" spellcheck="false" aria-label="${t("Buscar extensão")}">
        <div class="ext-list">${chips(info.php)}</div>
        ${info.zend.length ? `<div class="field-label">Zend</div><div class="ext-list">${chips(info.zend)}</div>` : ""}
        <p class="dim">${t("{n} módulos carregados.", { n: info.php.length })}${info.declared.length ? ` ${t("Personalizadas: {list}.", { list: esc(info.declared.join(", ")) })}` : ""}
          ${info.note ? t("Nesta versão: {note}.", { note: esc(info.note) }) : ""}</p>`,
      confirmLabel: t("Gerenciar no painel do Lerd"),
    });
    const search = [...document.querySelectorAll(".dialog [data-ext-search]")].pop();
    if (search) {
      search.addEventListener("input", () => {
        const q = search.value.trim().toLowerCase();
        search.closest(".dialog").querySelectorAll(".ext-chip").forEach((c) => { c.hidden = Boolean(q) && !c.dataset.name.includes(q); });
      });
      search.focus();
    }
    if (await pending) await post("/api/open", { kind: "dashboard" });
  }

  async openIni(version) {
    const result = await post(`/api/environment/php/${version}/ini/open`);
    await terminals.sync();
    this.options.navigate(`#/terminals/terminal/${result.id}`);
  }

  async phpAction(version, op) {
    const result = await post(`/api/environment/php/${encodeURIComponent(version)}/${op}`);
    if (result.id) {
      await terminals.sync();
      this.options.navigate(`#/terminals/terminal/${result.id}`);  // comando demorado: a aba mostra o andamento
      return;
    }
    if (result.ok) toast(t("PHP {version} agora é o padrão.", { version }), { kind: "ok" });
    else toast(t("PHP {version}: {msg}", { version, msg: (result.output || "").split("\n").pop() }), { kind: "error", timeout: 8000 });
    await this.load();
  }

  async onClick(event) {
    const node = event.target.closest("[data-node]");
    if (node) {
      this.nodeAction(node.dataset.node, node.dataset.op).catch(reportError);
      return;
    }
    if (event.target.closest("[data-action=install-node]")) {
      const value = this.root.querySelector("[data-node-new]").value.trim();
      if (value) this.nodeAction(value, "install").catch(reportError);
      return;
    }
    const xdebug = event.target.closest("[data-xdebug]");
    if (xdebug) {
      this.xdebugAction(xdebug.dataset.xdebug, Boolean(xdebug.dataset.on)).catch(reportError);
      return;
    }
    const ext = event.target.closest("[data-ext]");
    if (ext) {
      this.showExtensions(ext.dataset.ext).catch(reportError);
      return;
    }
    const ini = event.target.closest("[data-ini]");
    if (ini) {
      this.editIni(ini.dataset.ini).catch(reportError);
      return;
    }
    const php = event.target.closest("[data-php]");
    if (php) {
      try {
        await this.phpAction(php.dataset.php, php.dataset.op);
      } catch (err) {
        reportError(err);
      }
      return;
    }
    if (event.target.closest("[data-action=install-php]")) {
      try {
        await this.phpAction(this.root.querySelector("[data-install]").value, "install");
      } catch (err) {
        reportError(err);
      }
      return;
    }
    const target = event.target.closest("[data-action], [data-svc]");
    if (!target) return;
    try {
      if (target.dataset.action === "dashboard") await post("/api/open", { kind: "dashboard" });
      if (target.dataset.svc) await this.service(target.dataset.svc, target.dataset.op);
    } catch (err) {
      reportError(err);
    }
  }

  async service(name, op) {
    this.busy.add(name);
    this.render();
    try {
      const result = await post(`/api/environment/services/${encodeURIComponent(name)}/${op}`);
      if (!result.ok) toast(`${name}: ${(result.output || "").split("\n").pop()}`, { kind: "error", timeout: 8000 });
    } finally {
      this.busy.delete(name);
      await this.load();
    }
  }

  destroy() {
    this.stopTimer();
  }
}
