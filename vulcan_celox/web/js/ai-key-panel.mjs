// Anthropic key and model, shown in Settings. Used only when the user asks for a documentation.

import { confirmDialog } from "./ai.mjs";
import { del, patch, put } from "./api.mjs";
import { esc, icon, reportError, toast } from "./dom.mjs";
import { t } from "./i18n.mjs";

export class AiKeyPanel {
  constructor(box) {
    this.box = box;
    this.config = null;
    box.addEventListener("click", (e) => this.onClick(e));
    box.addEventListener("change", (e) => this.onChange(e));
    box.addEventListener("submit", (e) => this.onSubmit(e));
  }

  show(config) {
    this.config = config;
    this.render();
  }

  render() {
    const cfg = this.config;
    if (!cfg.configured) {
      this.box.innerHTML = `
        <form class="key-form" data-role="key-form" autocomplete="off">
          <p class="dim">${t("Usada só quando você pede uma documentação. Fica no cofre de senhas do sistema; o app nunca mostra nem grava a chave em arquivo.")}</p>
          <label class="field-label" for="ai-key">${t("Chave de API")}</label>
          <input id="ai-key" class="input" name="key" type="password" placeholder="sk-ant-…" spellcheck="false" autocomplete="off" required>
          <button class="btn btn-primary" type="submit">${icon("lock")}<span>${t("Validar e salvar")}</span></button>
        </form>`;
      return;
    }
    const models = cfg.models.length ? cfg.models : [{ id: cfg.model, name: cfg.model }];
    this.box.innerHTML = `
      <div class="key-form">
        <div class="key-row"><span class="badge badge-ok">${icon("check")}${t("ativa")}</span><span class="mono">${esc(cfg.masked)}</span><div class="spacer"></div>
          <button class="btn btn-ghost btn-sm" data-action="remove-key">${icon("trash")}<span>${t("Remover")}</span></button></div>
        <label class="field-label" for="ai-model">${t("Modelo")}</label>
        <select id="ai-model" class="select" data-role="model">
          ${models.map((m) => `<option value="${esc(m.id)}" ${m.id === cfg.model ? "selected" : ""}>${esc(m.name)}</option>`).join("")}
        </select>
      </div>`;
  }

  async onClick(event) {
    if (!event.target.closest("[data-action=remove-key]")) return;
    try {
      const ok = await confirmDialog({ title: t("Remover a chave da Anthropic?"), confirmLabel: t("Remover"),
        body: `<p>${t("A chave sai do cofre de senhas. As documentações já geradas continuam nos arquivos.")}</p>` });
      if (!ok) return;
      this.show(await del("/api/ai/key"));
      toast(t("Chave removida."), { kind: "ok" });
    } catch (err) {
      reportError(err);
    }
  }

  async onChange(event) {
    if (event.target.dataset.role !== "model") return;
    try {
      this.config = await patch("/api/ai/config", { model: event.target.value });
      toast(t("Modelo trocado para {model}.", { model: event.target.selectedOptions[0].textContent }), { kind: "ok" });
    } catch (err) {
      reportError(err);
      this.render();
    }
  }

  async onSubmit(event) {
    if (event.target.dataset.role !== "key-form") return;
    event.preventDefault();
    const input = event.target.elements.key;
    const button = event.target.querySelector("button[type=submit]");
    button.disabled = true;
    button.querySelector("span").textContent = t("Validando…");
    try {
      const config = await put("/api/ai/key", { key: input.value.trim() });
      input.value = "";
      this.show(config);
      toast(t("Chave validada e guardada no cofre de senhas."), { kind: "ok" });
    } catch (err) {
      input.value = "";
      reportError(err);
      button.disabled = false;
      button.querySelector("span").textContent = t("Validar e salvar");
    }
  }
}
