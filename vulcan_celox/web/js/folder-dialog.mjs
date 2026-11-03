// Diálogo "Abrir terminal em": pasta sugerida, digitação validada, recentes e seletor nativo do macOS.

import { get, hasBridge, native, patch } from "./api.mjs";
import { debounce, esc, icon } from "./dom.mjs";
import { loadThemes } from "./themes.mjs";

const AGENTS = [["claude", "Claude Code"], ["codex", "Codex"], ["shell", "Só o shell"]];

let pickSeq = 0;

export function pickNative(start) {
  return new Promise((resolve) => {
    const id = `p${++pickSeq}`;
    const onPicked = (event) => {
      if (!event.detail || event.detail.id !== id) return;
      window.removeEventListener("vulcan-folder-picked", onPicked);
      resolve(event.detail.path || null);
    };
    window.addEventListener("vulcan-folder-picked", onPicked);
    if (!native({ type: "pickFolder", id, start })) {
      window.removeEventListener("vulcan-folder-picked", onPicked);
      resolve(null);
    }
  });
}

/** Pasta sugerida para abrir direto: a do site, senão a mais recente, senão a pasta de início. */
export async function suggestedFolder(site = null) {
  if (site && site.path) return site.path;
  try {
    const data = await get("/api/fs/recent");
    return (data.recent[0] && data.recent[0].path) || data.home.path || "~";
  } catch {
    return "~";
  }
}

function themeCards(t, chosen) {
  const tabsByTheme = t.inUse || {};
  return t.list.map((theme) => {
    const used = (tabsByTheme[theme.id] || []).length;
    const status = theme.id === t.next ? "próximo da rotação" : used ? `em uso em ${used} ${used === 1 ? "aba" : "abas"}` : "livre";
    return `<button type="button" class="nt-theme t-${esc(theme.id)} ${theme.id === chosen ? "is-on" : ""}" data-theme="${esc(theme.id)}" aria-pressed="${theme.id === chosen}">
      <span class="nt-swatch"><span class="nt-prompt">❯</span> ${esc(theme.desc)}</span>
      <span class="nt-cap"><b>${esc(theme.name)}</b><span class="${theme.id === t.next ? "is-next" : used ? "is-used" : ""}">${status}</span></span></button>`;
  }).join("");
}

/**
 * Pergunta a pasta do terminal novo, o agente e o tema.
 * @param {{suggested?: string, site?: string}} options  suggested: caminho absoluto ou com ~
 * @returns {Promise<{cwd: string, title: string, theme: string, agent: string}|null>}
 */
export async function askFolder({ suggested = "", site = "" } = {}) {
  let data = { home: { path: "", short: "~" }, recent: [] };
  const [recent, t] = await Promise.all([get("/api/fs/recent").catch(() => null), loadThemes(true)]);
  if (recent) data = recent;  // sem recentes: o diálogo continua funcionando só com a digitação
  let theme = t.next || "homebrew";
  let agent = (t.newTerminal && t.newTerminal.agent) || "shell";
  const start = suggested || data.home.path || "~";
  return new Promise((resolve) => {
    const backdrop = document.createElement("div");
    backdrop.className = "dialog-backdrop";
    backdrop.innerHTML = `
      <form class="dialog folder-dialog" role="dialog" aria-modal="true" aria-labelledby="folder-title" autocomplete="off">
        <h2 id="folder-title">Abrir terminal em</h2>
        <p class="dim folder-sub">${site ? `Sessão do site <strong>${esc(site)}</strong>. ` : ""}Enter abre na pasta indicada.</p>
        <div class="folder-field">
          ${icon("folder")}
          <input name="path" class="folder-input" spellcheck="false" aria-label="Pasta" value="${esc(start)}">
          ${hasBridge ? `<button type="button" class="btn btn-sm" data-pick>Escolher…</button>` : ""}
        </div>
        <div class="folder-status" data-status aria-live="polite"></div>
        ${data.recent.length ? `<div class="folder-recent">
          <div class="field-label">Recentes</div>
          <ul>${data.recent.map((r) => `<li><button type="button" class="folder-option" data-path="${esc(r.path)}">
              ${icon("folder")}<span class="folder-name">${esc(r.name)}</span><span class="folder-path">${esc(r.short)}</span>
              ${r.site ? `<span class="folder-site">${esc(r.site)}</span>` : ""}</button></li>`).join("")}</ul>
        </div>` : ""}
        <label class="field-label" for="folder-name">Nome do terminal (opcional)</label>
        <input id="folder-name" name="title" class="input" maxlength="60" placeholder="usa o nome da pasta">
        ${t.list.length ? `<div class="field-label">Iniciar</div>
        <div class="segmented nt-agents" role="radiogroup" aria-label="Agente">${AGENTS.map(([id, label]) =>
          `<button type="button" class="seg ${id === agent ? "is-on" : ""}" data-agent="${id}" role="radio" aria-checked="${id === agent}">${label}</button>`).join("")}</div>
        <div class="field-label">Tema</div>
        <div class="nt-themes" data-themes>${themeCards(t, theme)}</div>
        <p class="nt-pair dim" data-pair></p>
        <label class="dialog-check nt-skip"><input type="checkbox" name="skip"><span>Não perguntar a pasta da próxima vez: o botão abre direto, já no próximo tema</span></label>` : ""}
        <div class="dialog-actions">
          <button type="button" class="btn" data-cancel>Cancelar</button>
          <button type="submit" class="btn btn-primary" data-ok>${icon("terminal")}<span>Abrir terminal</span></button>
        </div>
      </form>`;
    const form = backdrop.querySelector("form");
    const input = form.elements.path;
    const pair = backdrop.querySelector("[data-pair]");
    const describe = () => {
      if (!pair) return;
      const name = (t.byId[theme] || {}).name || theme;
      pair.innerHTML = `${icon("spark")}<span>A aba nasce em <b>${esc(name)}</b> com <code>VULCAN_SESSION_ID</code> e <code>VULCAN_THEME</code> no ambiente${
        agent === "shell" ? "." : `; o terminal digita <code>${agent}</code> e a sessão aparece pareada em Agentes em poucos segundos.`}</span>`;
    };
    describe();
    const status = backdrop.querySelector("[data-status]");
    const ok = backdrop.querySelector("[data-ok]");
    let resolved = null;
    let seq = 0;

    const check = async () => {
      const mine = ++seq;
      const value = input.value.trim();
      resolved = null;
      ok.disabled = true;
      if (!value) {
        status.className = "folder-status is-error";
        status.textContent = "Informe uma pasta.";
        return;
      }
      try {
        const info = await get(`/api/fs/folder?path=${encodeURIComponent(value)}`);
        if (mine !== seq) return;
        if (info.is_dir) {
          resolved = info.path;
          ok.disabled = false;
          status.className = "folder-status is-ok";
          status.innerHTML = `${icon("check")}<span>${esc(info.short)}</span>`;
        } else {
          status.className = "folder-status is-error";
          status.textContent = info.exists ? "Isso é um arquivo, não uma pasta." : "Pasta não encontrada.";
        }
      } catch (err) {
        if (mine !== seq) return;
        status.className = "folder-status is-error";
        status.textContent = err.message || "Não foi possível verificar a pasta.";
      }
    };
    const checkSoon = debounce(check, 180);

    const finish = (value) => {
      document.removeEventListener("keydown", onKey, true);
      backdrop.remove();
      resolve(value);
    };
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        finish(null);
      }
    };

    input.addEventListener("input", checkSoon);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!resolved) await check();
      if (!resolved) return;
      const skip = form.elements.skip && form.elements.skip.checked;
      patch("/api/preferences", { new_terminal: { agent, ...(skip ? { skip_folder: true } : {}) } }).catch(() => null);
      // o tema sugerido gasta a rotação ("auto"); um tema escolhido à mão não
      finish({ cwd: resolved, title: form.elements.title.value.trim(), theme: theme === t.next ? "auto" : theme, agent });
    });
    backdrop.addEventListener("click", async (e) => {
      if (e.target === backdrop || e.target.closest("[data-cancel]")) return finish(null);
      const themeBtn = e.target.closest("[data-theme]");
      if (themeBtn) {
        theme = themeBtn.dataset.theme;
        backdrop.querySelectorAll("[data-theme]").forEach((b) => {
          b.classList.toggle("is-on", b === themeBtn);
          b.setAttribute("aria-pressed", String(b === themeBtn));
        });
        describe();
        return null;
      }
      const agentBtn = e.target.closest("[data-agent]");
      if (agentBtn) {
        agent = agentBtn.dataset.agent;
        backdrop.querySelectorAll("[data-agent]").forEach((b) => {
          b.classList.toggle("is-on", b === agentBtn);
          b.setAttribute("aria-checked", String(b === agentBtn));
        });
        describe();
        return null;
      }
      const option = e.target.closest("[data-path]");
      if (option) {
        input.value = option.dataset.path;
        await check();
        input.focus();
        return null;
      }
      if (e.target.closest("[data-pick]")) {
        const path = await pickNative(resolved || input.value.trim());
        if (path) {
          input.value = path;
          await check();
        }
        input.focus();
      }
      return null;
    });
    document.addEventListener("keydown", onKey, true);
    document.body.appendChild(backdrop);
    input.focus();
    input.select();
    check();
  });
}
