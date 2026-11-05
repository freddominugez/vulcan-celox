// Configurações screen: what the sidebar shows, appearance, startup, notices, the Anthropic key and the app's data.

import { AiKeyPanel } from "../ai-key-panel.mjs";
import { DataPanel, updateRow } from "./settings-data.mjs";
import { get, patch, post, put } from "../api.mjs";
import { NAV_GROUPS, SIDE_SECTIONS, app, lerdUnavailable, navById } from "../app-state.mjs";
import { noticesEnabled, setNoticesEnabled } from "../attention-notify.mjs";
import { esc, icon, reportError, toast } from "../dom.mjs";
import { currentLanguage, t } from "../i18n.mjs";
import { prEnabled, setPrEnabled } from "../pr-status.mjs";
import { isHidden, setHidden } from "../sidebar-prefs.mjs";
import { THEME_OPTIONS, setThemePref, themePref } from "../theme.mjs";
import { themes } from "../themes.mjs";

const LANGUAGES = [["en", "English"], ["pt", t("Português")]];

const toggle = (key, checked, title, text) => `<label class="cf-row"><input type="checkbox" data-cf="${key}" ${checked ? "checked" : ""}>
  <span class="cf-text"><b>${esc(title)}</b>${text ? `<span class="dim">${esc(text)}</span>` : ""}</span></label>`;

export class SettingsView {
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.root.addEventListener("change", (e) => this.onChange(e));
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.root.innerHTML = `<div class="loading"><span class="skeleton w-40"></span><span class="skeleton w-70"></span></div>`;
    this.load();
  }

  async load() {
    try {
      const [prefs, guide, config, update] = await Promise.all([patch("/api/preferences", {}), get("/api/guide"), get("/api/ai/config"), get("/api/update")]);
      this.prefs = prefs;
      this.guide = guide;
      this.update = update;
      this.render();
      this.mountPanels(config);
    } catch (err) {
      reportError(err);
    }
  }

  mountPanels(config) {
    this.keyPanel = new AiKeyPanel(this.root.querySelector("[data-role=key]"));
    this.keyPanel.show(config);
    this.dataPanel = new DataPanel(this.root.querySelector("[data-role=data]"), this.prefs.data_dir);
  }

  sidebarHtml() {
    const row = (n) => `<label class="cf-row ${n.locked ? "is-locked" : ""}"><input type="checkbox" data-side="${n.id}" ${!isHidden(n.id) ? "checked" : ""} ${n.locked ? "disabled" : ""}>
      <span class="cf-text"><b>${esc(n.label)}</b><span class="dim">${esc(n.desc)}${n.locked ? ` ${t("Sempre visível, para você poder voltar aqui.")}` : ""}</span></span></label>`;
    const groups = NAV_GROUPS.map((g) => {
      const items = g.items.map((id) => navById[id]).filter((n) => !(n.id === "ambiente" && lerdUnavailable()));
      return `<div class="cf-group"><h3>${esc(g.label || g.title)}</h3>${items.map(row).join("")}</div>`;
    }).join("");
    return `${groups}<div class="cf-group"><h3>${t("Listas abaixo do menu")}</h3>${SIDE_SECTIONS.map(row).join("")}</div>`;
  }

  render() {
    const p = this.prefs;
    const auto = app.state && app.state.autostart;
    const canLerd = !lerdUnavailable();
    const choice = (name, options, current) => `<div class="segmented cf-seg" role="group">${options.map(([id, label]) => `<button type="button" class="seg ${id === current ? "is-on" : ""}" data-${name}="${id}" aria-pressed="${id === current}">${esc(label)}</button>`).join("")}</div>`;
    this.root.innerHTML = `<div class="page cf-page">
      <h1 class="cf-title">${t("Configurações")}</h1>
      <section class="panel cf-panel"><header class="panel-head"><h2>${t("Barra lateral")}</h2>
          <button class="btn btn-ghost btn-sm" data-cf-action="sidebar-reset">${icon("restart")}<span>${t("Mostrar tudo")}</span></button></header>
        <p class="dim cf-note">${t("Escolha o que aparece. O que você esconder continua na busca (⌘K).")}</p>
        <div class="cf-groups">${this.sidebarHtml()}</div></section>
      <section class="panel cf-panel"><header class="panel-head"><h2>${t("Aparência")}</h2></header>
        <div class="cf-line"><b>${t("Tema")}</b>${choice("theme", THEME_OPTIONS, themePref())}</div>
        <div class="cf-line"><b>${t("Idioma")}</b>${choice("lang", LANGUAGES, currentLanguage())}</div></section>
      <section class="panel cf-panel"><header class="panel-head"><h2>${t("Ao iniciar")}</h2></header>
        ${toggle("welcome", !this.guide.skipped, t("Mostrar a tela de abertura"), t("O Início explica cada item e confere o que falta configurar."))}
        ${canLerd ? toggle("autostart", Boolean(auto && auto.enabled), t("Ligar o Lerd junto com o app"), t("Só faz sentido se você usa sites PHP.")) : ""}
        ${toggle("ask-folder", !(p.new_terminal && p.new_terminal.skip_folder), t("Perguntar a pasta ao abrir um terminal"), t("Desligado, o terminal abre direto na pasta do projeto atual."))}</section>
      <section class="panel cf-panel"><header class="panel-head"><h2>${t("Avisos e rede")}</h2></header>
        ${toggle("notices", noticesEnabled(), t("Avisar quando um agente espera por você"), t("Notificação do sistema, com a janela em segundo plano."))}
        ${toggle("pr", prEnabled(), t("Consultar o estado do PR no GitHub"), t("Usa a rede e o comando gh. Desligado, o estado é estimado pelos comandos da sessão."))}
        ${toggle("update", this.update.enabled, t("Avisar quando houver versão nova"), t("Consulta o GitHub no máximo uma vez por dia. Só lê o número da versão: não baixa nem instala nada."))}</section>
      <section class="panel cf-panel"><header class="panel-head"><h2>${t("Chave da Anthropic")}</h2></header>
        <div data-role="key"></div></section>
      <section class="panel cf-panel"><header class="panel-head"><h2>${t("Backup e segredos")}</h2></header>
        <div data-role="data"></div></section>
      <section class="panel cf-panel"><header class="panel-head"><h2>${t("Sobre")}</h2></header>
        ${updateRow(this.update)}
        <div class="cf-line"><b>${t("Seus dados")}</b><span class="mono cf-path" title="${esc(p.data_dir)}">${esc(p.data_dir)}</span>
          <button class="btn btn-ghost btn-sm" data-cf-action="open-data">${icon("folder")}<span>${t("Abrir pasta")}</span></button></div>
        <p class="dim cf-note"><a href="#/ajuda">${t("Ajuda: manual e perguntas frequentes")}</a></p></section>
    </div>`;
  }

  async onChange(event) {
    const target = event.target;
    try {
      if (target.dataset.side) {
        const hidden = [...this.root.querySelectorAll("[data-side]")].filter((i) => !i.checked && !i.disabled).map((i) => i.dataset.side);
        await setHidden(hidden);
        return;
      }
      const key = target.dataset.cf;
      if (key === "welcome") this.guide = await put("/api/guide", { skipped: !target.checked });
      if (key === "autostart") {
        const data = await patch("/api/preferences", { autostart_env: target.checked });
        if (app.state) app.state.autostart = data.autostart;
        this.options.onChange();
      }
      if (key === "ask-folder") {
        this.prefs = await patch("/api/preferences", { new_terminal: { skip_folder: !target.checked } });
        themes.newTerminal = this.prefs.new_terminal;
      }
      if (key === "notices") await setNoticesEnabled(target.checked);
      if (key === "pr") await setPrEnabled(target.checked);
      if (key === "update") this.update = await put("/api/update", { enabled: target.checked });
    } catch (err) {
      target.checked = !target.checked;
      reportError(err);
    }
  }

  async onClick(event) {
    const button = event.target.closest("button");
    if (!button) return;
    try {
      if (button.dataset.theme) {
        await setThemePref(button.dataset.theme);
        this.render();
        this.mountPanels(await get("/api/ai/config"));
      }
      if (button.dataset.lang && button.dataset.lang !== currentLanguage()) {
        await patch("/api/preferences", { language: button.dataset.lang });
        location.reload();
      }
      if (button.dataset.cfAction === "sidebar-reset") {
        await setHidden([]);
        this.root.querySelectorAll("[data-side]").forEach((i) => { i.checked = true; });
        toast(t("A barra lateral voltou a mostrar tudo."), { kind: "ok" });
      }
      if (button.dataset.cfAction === "update-open") await post("/api/open", { kind: "url", target: this.update.url });
      if (button.dataset.cfAction === "update-check") {
        this.update = await post("/api/update/check", {});
        const row = this.root.querySelector("[data-role=update]");
        if (row) row.outerHTML = updateRow(this.update);
        if (!this.update.reason && !this.update.newer) toast(t("Você está na versão mais recente."), { kind: "ok" });
      }
      if (button.dataset.cfAction === "open-data") await post("/api/open", { kind: "finder", target: this.prefs.data_dir });
    } catch (err) {
      reportError(err);
    }
  }
}
