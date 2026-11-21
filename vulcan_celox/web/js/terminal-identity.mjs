// Edit the label of a running terminal using the existing named colors.
import { esc, icon } from "./dom.mjs";
import { t } from "./i18n.mjs";
import { terminals } from "./terminal-pool.mjs";
import { themes, loadThemes } from "./themes.mjs";

export async function editTerminalIdentity(id, trigger) {
  await loadThemes();
  const terminal = terminals.get(id);
  if (document.getElementById("terminal-identity")) return;
  if (!terminal?.alive) throw new Error(t("Terminal encerrado"));
  const { title, tab_color: color } = terminal.info;
  const dialog = document.createElement("dialog");
  dialog.className = "dialog session-dialog";
  dialog.id = "terminal-identity";
  dialog.setAttribute("aria-labelledby", "terminal-identity-title");
  const choices = [{ id: "", name: t("Cor do tema") }, ...themes.list];
  dialog.innerHTML = `
    <form>
      <h2 id="terminal-identity-title">${t("Nome e cor da aba")}</h2>
      <div class="dialog-body identity-fields">
        <label class="field-label" for="terminal-label">${t("Nome do terminal")}</label>
        <input name="title" id="terminal-label" class="input" maxlength="60" value="${esc(title)}" required autofocus>
        <fieldset class="identity-colors">
          <legend class="field-label">${t("Cor da aba")}</legend>
          ${choices.map((option) => `<label class="t-${esc(option.id || terminal.info.theme || "default")}">
            <input type="radio" name="color" value="${esc(option.id)}" ${option.id === (color || "") ? "checked" : ""}>
            <span class="session-color" aria-hidden="true"></span><span>${esc(option.name)}</span></label>`).join("")}
        </fieldset>
        <p class="session-dialog-error" role="alert" hidden></p>
      </div>
      <div class="dialog-actions">
        <button type="button" class="btn" data-cancel>${t("Cancelar")}</button>
        <button class="btn btn-primary" type="submit">${icon("check")}${t("Salvar alterações")}</button>
      </div>
    </form>`;
  const form = dialog.querySelector("form");
  const name = form.elements.title;
  const error = dialog.querySelector("[role=alert]");
  const save = form.querySelector("[type=submit]");
  const cancel = form.querySelector("[data-cancel]");
  cancel.addEventListener("click", () => dialog.close());
  dialog.addEventListener("cancel", (event) => {
    if (save.disabled) event.preventDefault();
  });
  dialog.addEventListener("close", () => {
    dialog.remove();
    if (trigger?.isConnected) trigger.focus();
    else (document.querySelector(`[data-identity="${CSS.escape(id)}"], .tab[data-id="${CSS.escape(id)}"]`)
      || document.querySelector("#side-terminal-head a, #side-collapse"))?.focus({ preventScroll: true });
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const nextTitle = name.value.trim();
    if (!nextTitle) {
      name.value = "";
      name.reportValidity();
      return;
    }
    error.hidden = true;
    save.disabled = cancel.disabled = true;
    try {
      await terminals.updateIdentity(id, { title: nextTitle, tab_color: form.elements.color.value || null });
      dialog.close();
    } catch (err) {
      error.textContent = err.status === 409 || err.status === 404 ? t("Terminal encerrado") : t(err.message);
      error.hidden = false;
    } finally {
      save.disabled = cancel.disabled = false;
    }
  });
  document.body.appendChild(dialog);
  dialog.showModal();
  name.select();
}
