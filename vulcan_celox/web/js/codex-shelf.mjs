import { drafts } from "./codex-drafts.mjs";
import { t } from "./i18n.mjs";

export function openDraftShelf(composer, trigger) {
  if (document.querySelector(".codex-shelf")) return;
  const dialog = document.createElement("dialog");
  dialog.className = "dialog session-dialog codex-shelf";
  dialog.setAttribute("aria-label", t("Rascunhos desta janela"));
  dialog.innerHTML = `
    <h2>${t("Rascunhos desta janela")}</h2>
    <div class="dialog-body"></div>
    <div class="dialog-actions"><button type="button" class="btn" data-close>${t("Fechar")}</button></div>`;
  const body = dialog.querySelector(".dialog-body");
  const close = dialog.querySelector("[data-close]");
  const button = (label, run) => {
    const el = document.createElement("button");
    el.type = "button";
    el.className = "btn btn-sm";
    el.textContent = label;
    el.addEventListener("click", run);
    return el;
  };

  const paint = () => {
    body.replaceChildren();
    const items = drafts.list();
    if (!items.length) {
      body.textContent = t("Nenhum rascunho nesta janela.");
      return;
    }
    for (const draft of items) {
      const details = document.createElement("details");
      const heading = document.createElement("summary");
      const { origin, terminal } = draft;
      heading.textContent = [`${origin.label} · ${origin.id}`, origin.root || origin.cwd,
        terminal ? t("Destino {id}", { id: terminal.id }) : t("Nenhum destino escolhido.")].filter(Boolean).join(" · ");
      const preview = document.createElement("textarea");
      preview.className = "input";
      preview.readOnly = true;
      preview.rows = 3;
      preview.setAttribute("aria-label", t("Rascunho Codex"));
      preview.value = draft.text;
      const discard = button(t("Descartar rascunho"), () => {
        draft.text = "";
        if (composer?.draft === draft) composer.renderDraft();
        paint();
        close.focus();
      });
      details.append(heading, preview, discard);
      if (composer?.draft && composer.draft !== draft && !composer.draft.text) {
        details.append(button(t("Transferir para o rascunho atual"), () => {
          if (drafts.transfer(draft, composer.draft)) {
            composer.renderDraft();
            dialog.close();
          }
        }));
      }
      body.append(details);
    }
  };

  close.addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    dialog.remove();
    if (trigger.isConnected) trigger.focus();
  });
  paint();
  document.body.append(dialog);
  dialog.showModal();
}
