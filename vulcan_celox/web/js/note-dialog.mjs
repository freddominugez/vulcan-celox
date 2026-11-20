// Sticky-note editor shared by the notebook and the sidebar.
import { get, patch } from "./api.mjs";
import { esc, icon, reportError } from "./dom.mjs";
import { t } from "./i18n.mjs";
import { sessionHash, terminals } from "./terminal-pool.mjs";

export function noteSessionLabel(session) {
  return `<span class="session-color t-${esc(session.tab_color || session.theme || "default")}" aria-hidden="true"></span>
    <span class="note-terminal-name">${esc(session.title)}</span>`;
}

export async function openNote(id, trigger, onChange) {
  if (document.getElementById("note-dialog")) return;
  const url = `/api/notes/${encodeURIComponent(id)}`;
  const note = await get(url);
  if (document.getElementById("note-dialog")) return;

  const dialog = document.createElement("dialog");
  dialog.className = "dialog session-dialog note-dialog";
  dialog.id = "note-dialog";
  dialog.setAttribute("aria-labelledby", "note-dialog-title");
  dialog.innerHTML = `
    <header class="note-dialog-head">
      <h2 id="note-dialog-title">${t("Post-it")}</h2>
      <button type="button" class="icon-btn" data-note-close aria-label="${t("Fechar")}">${icon("x")}</button>
    </header>
    <div class="dialog-body">
      <div class="note-terminal-context"></div>
      <label class="field-label" for="note-editor">${t("Texto do post-it")}</label>
      <textarea id="note-editor" class="input" rows="8" autofocus></textarea>
      <p class="note-save-status" role="status"></p>
      <p class="session-dialog-error" role="alert" hidden></p>
    </div>
    <div class="dialog-actions"><button type="button" class="btn btn-primary" data-note-close>${t("Fechar")}</button></div>`;
  const editor = dialog.querySelector("#note-editor");
  const context = dialog.querySelector(".note-terminal-context");
  const status = dialog.querySelector("[role=status]");
  const error = dialog.querySelector("[role=alert]");
  editor.value = note.text;
  let session = note.session;
  let saved = note.text;
  let changed = false;
  let timer;
  let queue = Promise.resolve();
  let closing = false;

  function renderSession(linked) {
    session = linked;
    if (session) {
      context.innerHTML = `
        <div><span class="field-label">${t("Terminal vinculado")}</span>
          <span class="note-terminal-label">${noteSessionLabel(session)}</span>
        </div>
        <a class="btn btn-sm" href="${sessionHash(session, "terminal", session.open ? "" : "historico")}" data-note-terminal>
          ${icon(session.open ? "terminal" : "clock")}${session.open ? t("Ir para o terminal") : t("Ver no Histórico")}
        </a>`;
      return;
    }

    const options = terminals.list(note.site || null).filter((terminal) => terminal.alive);
    context.innerHTML = options.length ? `
      <label for="note-terminal-choice">${t("Vincular a um terminal aberto")}</label>
      <div class="note-terminal-picker">
        <select class="select" id="note-terminal-choice">
          <option value="">${t("Escolha um terminal")}</option>
          ${options.map(({ info }) => `<option value="${esc(info.id)}">${esc(info.title)}${info.cwd ? ` · ${esc(info.cwd)}` : ""}</option>`).join("")}
        </select>
        <button type="button" class="btn btn-sm" data-link-note disabled>${t("Vincular")}</button>
      </div>` : `<span>${t("Sem terminal vinculado")}</span>`;
  }

  function showError(err) {
    error.textContent = t(err.message);
    error.hidden = false;
    status.textContent = "";
  }

  function persist(fields = {}) {
    const text = editor.value;
    const write = async () => {
      if (saved === text && !Object.keys(fields).length) return;
      error.hidden = true;
      status.textContent = t("Salvando…");
      const updated = await patch(url, { ...fields, ...(text === saved ? {} : { text }) });
      saved = updated.text;
      changed = true;
      status.textContent = t("Salvo");
      if (fields.link_terminal) renderSession(updated.session);
    };
    queue = queue.catch(() => {}).then(write);
    return queue;
  }

  async function close(destination = "") {
    if (closing) return;
    closing = true;
    clearTimeout(timer);
    editor.disabled = true;
    try {
      await persist();
      if (destination) await terminals.sync();
      dialog.close();
      if (destination) {
        location.hash = destination;
        if (session?.open && terminals.popped.has(session.id)) terminals.focusPopout(session.id);
      }
    } catch (err) {
      showError(err);
      editor.disabled = false;
      editor.focus();
    } finally {
      closing = false;
    }
  }

  editor.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => persist().catch(showError), 500);
  });
  dialog.addEventListener("change", (event) => {
    if (event.target.id === "note-terminal-choice") {
      dialog.querySelector("[data-link-note]").disabled = !event.target.value;
    }
  });
  dialog.addEventListener("click", async (event) => {
    if (event.target.closest("[data-note-close]")) close();
    const terminal = event.target.closest("[data-note-terminal]");
    if (terminal) {
      event.preventDefault();
      close(terminal.hash);
    }
    const link = event.target.closest("[data-link-note]");
    if (!link || closing) return;
    clearTimeout(timer);
    link.disabled = true;
    const select = context.querySelector("select");
    select.disabled = true;
    try {
      await persist({ link_terminal: select.value });
    } catch (err) {
      showError(err);
      link.disabled = select.disabled = false;
    }
  });
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });
  dialog.addEventListener("close", async () => {
    dialog.remove();
    if (trigger?.isConnected) trigger.focus({ preventScroll: true });
    if (changed) {
      window.dispatchEvent(new CustomEvent("vulcan-note-changed"));
      try {
        await onChange?.();
      } catch (err) {
        reportError(err);
      }
    }
  });
  renderSession(note.session);
  document.body.appendChild(dialog);
  dialog.showModal();
}
