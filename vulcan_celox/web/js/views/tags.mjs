// Tags: criar, renomear, trocar cor, ver uso e progresso, excluir.

import { del, get, patch, post } from "../api.mjs";
import { $, esc, icon, progressBar, reportError, toast } from "../dom.mjs";
import { t } from "../i18n.mjs";

export class TagsView {
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.tags = [];
    this.palette = [];
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.root.addEventListener("submit", (e) => this.onSubmit(e));
    this.root.addEventListener("change", (e) => this.onRename(e));
    this.load();
  }

  async load() {
    try {
      const data = await get("/api/tags");
      this.tags = data.tags;
      this.palette = data.palette;
      this.render();
    } catch (err) {
      reportError(err);
    }
  }

  render() {
    const rows = this.tags.map((tag) => `
      <tr data-id="${tag.id}">
        <td class="col-swatch"><button class="tag-swatch" style="--chip:${esc(tag.color)}" data-action="color" aria-label="${t("Trocar cor de {name}", { name: esc(tag.name) })}" title="${t("Trocar cor")}"></button></td>
        <td><input class="input input-inline" value="${esc(tag.name)}" data-role="name" aria-label="${t("Nome da tag")}"></td>
        <td class="num">${tag.usage}</td>
        <td class="col-progress">${tag.progress ? `${progressBar(tag.progress)}<span class="num dim">${esc(tag.progress.label)}</span>` : `<span class="dim">${t("sem tarefas")}</span>`}</td>
        <td class="col-actions"><button class="icon-btn" data-action="delete" aria-label="${t("Excluir tag {name}", { name: esc(tag.name) })}">${icon("trash")}</button></td>
      </tr>`).join("");
    this.root.innerHTML = `
      <div class="page">
        <form class="inline-form" autocomplete="off">
          <input name="name" class="input" placeholder="${t("Nova tag")}" aria-label="${t("Nome da nova tag")}" required>
          <button class="btn btn-primary" type="submit">${icon("plus")}<span>${t("Criar tag")}</span></button>
        </form>
        ${this.tags.length ? `
        <table class="table">
          <thead><tr><th class="col-swatch"></th><th>${t("Nome")}</th><th class="num">${t("Itens")}</th><th>${t("Tarefas")}</th><th></th></tr></thead>
          <tbody>${rows}</tbody>
        </table>` : `<div class="empty-inline">${icon("tag")}<span>${t("Nenhuma tag ainda. Tags criadas em tarefas e post-its aparecem aqui.")}</span></div>`}
      </div>`;
  }

  async onSubmit(event) {
    event.preventDefault();
    const name = event.target.name.value.trim();
    if (!name) return;
    try {
      await post("/api/tags", { name });
      await this.load();
      $("input[name=name]", this.root).focus();
    } catch (err) {
      reportError(err);
    }
  }

  async onRename(event) {
    if (event.target.dataset.role !== "name") return;
    const id = event.target.closest("tr").dataset.id;
    try {
      await patch(`/api/tags/${id}`, { name: event.target.value });
      await this.load();
      this.options.onChange();
    } catch (err) {
      reportError(err);
      this.load();
    }
  }

  async onClick(event) {
    const target = event.target.closest("[data-action]");
    if (!target) return;
    const row = target.closest("tr");
    const tag = this.tags.find((t) => t.id === row.dataset.id);
    try {
      if (target.dataset.action === "color") {
        const next = this.palette[(this.palette.indexOf(tag.color) + 1) % this.palette.length];
        await patch(`/api/tags/${tag.id}`, { color: next });
      }
      if (target.dataset.action === "delete") {
        const result = await del(`/api/tags/${tag.id}`);
        toast(result.affected === 1 ? t("Tag “{name}” excluída de 1 item", { name: tag.name }) : t("Tag “{name}” excluída de {n} itens", { name: tag.name, n: result.affected }), { kind: "ok" });
      }
      await this.load();
      this.options.onChange();
    } catch (err) {
      reportError(err);
    }
  }

  destroy() {}
}
