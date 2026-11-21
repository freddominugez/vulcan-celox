import { copyToClipboard } from "./agents-ui.mjs";
import { get } from "./api.mjs";
import { clearTab } from "./attention-state.mjs";
import { drafts, validateDraft } from "./codex-drafts.mjs";
import { esc } from "./dom.mjs";
import { t } from "./i18n.mjs";
import { sessionHash, terminals } from "./terminal-pool.mjs";

const choices = () => terminals.live();
const destination = ({ id, title, cwd }) => `${title} · ${cwd} · ${id}`;
const checkTarget = (id) => get(`/api/agents/paired?terminal=${encodeURIComponent(id)}&foreground=1`);
const pairedId = (data) => data.session?.agent === "codex" ? data.session.id : null;

export class CodexComposer {
  constructor(code, host) {
    this.code = code;
    this.host = host;
    this.turn = 0;
    host.innerHTML = `
      <label class="field-label">${t("Rascunho Codex")}
        <textarea class="input codex-input" rows="3" spellcheck="false" autocomplete="off"></textarea>
      </label>
      <div class="codex-actions">
        <button type="button" class="btn btn-sm" data-codex="copy">${t("Copiar prompt")}</button>
        <button type="button" class="btn btn-sm" data-codex="select" hidden>${t("Selecionar rascunho")}</button>
        <button type="button" class="btn btn-sm" data-codex="open">${t("Abrir terminal")}</button>
        <button type="button" class="btn btn-sm" data-codex="choose" aria-expanded="false">${t("Escolher terminal")}</button>
      </div>
      <div class="codex-destination" aria-live="polite"></div>
      <div class="codex-picker" hidden>
        <label>${t("Terminal de destino")} <select class="select"></select></label>
        <label class="codex-verify"><input type="checkbox"> ${t("Abri ou retomei o Codex nesta aba.")}</label>
        <button type="button" class="btn btn-sm" data-codex="confirm">${t("Confirmar destino")}</button>
      </div>
      <p class="codex-status" role="status"></p>`;
    this.area = host.querySelector("textarea");
    this.statusId = "codex-draft-status";
    this.area.setAttribute("aria-describedby", this.statusId);
    this.picker = host.querySelector(".codex-picker");
    this.select = this.picker.querySelector("select");
    this.checked = this.picker.querySelector("input");
    this.status = host.querySelector(".codex-status");
    this.status.id = this.statusId;
    this.dest = host.querySelector(".codex-destination");
    this.area.addEventListener("input", () => {
      if (!this.draft) return;
      this.turn += 1;
      this.draft.text = this.area.value;
      this.button("select").hidden = true;
      this.validate();
    });
    this.select.addEventListener("change", () => {
      this.turn += 1;
      this.checked.checked = false;
      this.message("");
      this.button("confirm").disabled = !this.select.value;
    });
    host.addEventListener("click", (event) => {
      const action = event.target.closest("[data-codex]")?.dataset.codex;
      if (action === "copy") this.copy();
      if (action === "select") this.selectDraft();
      if (action === "choose") this.showPicker(this.picker.hidden);
      if (action === "confirm") this.confirm();
      if (action === "open") this.open();
    });
    this.unsubscribe = terminals.subscribe(() => this.paintTarget());
  }

  button(action) { return this.host.querySelector(`[data-codex="${action}"]`); }

  sync() {
    const { id, root } = this.code;
    const terminal = terminals.get(id);
    if (!terminal || this.origin?.id === id && this.origin.root === root) return;
    this.turn += 1;
    this.origin = { id, root, label: terminal.info.title, cwd: terminal.info.cwd };
    this.draft = drafts.draft(this.origin);
    this.verified = false;
    this.renderDraft();
  }

  renderDraft() {
    this.area.value = this.draft.text;
    this.showPicker(false);
    this.button("select").hidden = true;
    this.validate();
    this.paintTarget();
  }

  message(text) { this.status.textContent = text; }

  validate() {
    const result = validateDraft(this.area.value);
    const errors = {
      control: t("O rascunho contém caracteres de controle inválidos."),
      size: t("O rascunho pode ter até 4.000 caracteres Unicode."),
    };
    this.area.setAttribute("aria-invalid", String(Boolean(errors[result.error])));
    this.button("copy").disabled = Boolean(result.error);
    this.message(errors[result.error] || "");
    return result;
  }

  paintTarget() {
    const target = this.draft?.terminal;
    const session = target && terminals.get(target.id)?.info;
    const text = target ? destination(session || target) : t("Nenhum destino escolhido.");
    const state = target && (!session?.alive || terminals.stale) ? t("Destino indisponível. Verifique a aba.") : "";
    const pairing = this.draft?.pairing;
    const hint = pairing ? t("Sessão Codex sugerida: {id}", { id: pairing }) : "";
    const chosen = this.draft?.session ? t("Sessão Codex selecionada: {id}", { id: this.draft.session }) : hint;
    const label = [text, state, chosen].filter(Boolean).join(" · ");
    if (this.dest.textContent !== label) this.dest.textContent = label;
    if (!this.picker.hidden) this.paintChoices();
  }

  paintChoices() {
    const current = this.select.value;
    const html = `<option value="">${t("Escolha uma aba")}</option>` + choices().map(({ info }) =>
      `<option value="${esc(info.id)}">${esc(destination(info))}</option>`).join("");
    if (this.select.markup !== html) {
      this.select.innerHTML = html;
      this.select.markup = html;
      this.select.value = [...this.select.options].some(({ value }) => value === current) ? current : "";
    }
    this.button("confirm").disabled = !this.select.value;
  }

  showPicker(show, id = "") {
    this.picker.hidden = !show;
    this.button("choose").setAttribute("aria-expanded", String(show));
    if (!show) return;
    this.paintChoices();
    this.select.value = id && choices().some(({ info }) => info.id === id) ? id : "";
    this.checked.checked = false;
    this.button("confirm").disabled = !this.select.value;
    this.select.focus();
  }

  context() {
    return { turn: ++this.turn, ticket: this.code.ticket, root: this.code.root, draft: this.draft };
  }

  still({ turn, ticket, root, draft }) {
    return turn === this.turn && draft === this.draft && this.code.inContext(ticket, root);
  }

  async copy() {
    const { error, text } = this.validate();
    if (error) return;
    const action = this.context();
    const state = await copyToClipboard(text);
    if (!this.still(action)) return;
    this.button("select").hidden = state === "copied";
    this.message(state === "copied" ? t("Copiado") : state === "unconfirmed"
      ? t("Confira a área de transferência") : t("Selecione o rascunho e use o atalho de cópia."));
    if (state === "denied") this.selectDraft();
  }

  selectDraft() {
    this.area.focus();
    this.area.select();
  }

  async probe(id, action) {
    try {
      const data = await checkTarget(id);
      if (this.still(action)) return data;
    } catch {
      if (this.still(action)) this.message(t("Destino indisponível. Verifique a aba."));
    }
    return null;
  }

  async confirm() {
    const id = this.select.value;
    if (!id || !this.draft) return;
    const action = this.context();
    const data = await this.probe(id, action);
    if (!data) return;
    const target = terminals.get(id);
    if (!target?.alive || terminals.stale || data.foreground === "closed") return this.message(t("Destino indisponível. Verifique a aba."));
    if (data.foreground === "other") return this.message(t("Abra ou retome o Codex na aba escolhida e confirme novamente."));
    if (data.foreground !== "codex" && !this.checked.checked) return this.message(t("Confira o Codex em primeiro plano e confirme a aba."));
    const pairing = pairedId(data);
    this.draft = drafts.bind(this.origin, { ...target.info }, { pairing, session: data.chosen === pairing ? pairing : null });
    this.verified = true;
    this.confirmedForeground = data.foreground;
    this.renderDraft();
    this.button("open").focus();
  }

  async open() {
    const id = this.draft?.terminal?.id;
    if (!id || !this.verified) {
      this.showPicker(true, id);
      return;
    }
    const action = this.context();
    const data = await this.probe(id, action);
    if (!data) return;
    const terminal = terminals.get(id);
    if (!terminal?.alive || terminals.stale || data.foreground === "closed") {
      this.verified = false;
      this.paintTarget();
      return this.message(t("Destino indisponível. Verifique a aba."));
    }
    if (data.foreground === "other" || pairedId(data) !== this.draft.pairing ||
        (data.foreground === "unknown" && this.confirmedForeground !== "unknown")) {
      this.verified = false;
      this.showPicker(true, id);
      return this.message(t("O estado do Codex mudou. Confira a aba e confirme o destino novamente."));
    }
    if (data.foreground === "unknown") this.verified = false;  // a subsequent opening requires another manual check
    this.message(t("Confira o campo do Codex, cole o rascunho e envie pela CLI."));
    clearTab(id);
    if (terminals.popped.has(id)) terminals.focusPopout(id);
    else if (this.code.ws.sessions().includes(terminal)) this.code.focusDestination(id);
    else location.hash = sessionHash(terminal.info);
  }

  destroy() {
    this.turn += 1;
    this.unsubscribe();
    this.host.remove();
  }
}

