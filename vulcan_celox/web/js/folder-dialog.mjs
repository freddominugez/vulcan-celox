// "Abrir terminal em" dialog: suggested folder, validated typing, recents and the native macOS picker.

import { get, hasBridge, native, patch } from "./api.mjs";
import { debounce, esc, icon } from "./dom.mjs";
import { loadThemes } from "./themes.mjs";
import { t } from "./i18n.mjs";

const AGENTS = [["claude", "Claude Code"], ["codex", "Codex"], ["shell", t("Só o shell")]];

let pickSeq = 0;

export function pickNative(start, purpose = null) {
  return new Promise((resolve) => {
    const id = `p${++pickSeq}`;
    const onPicked = (event) => {
      if (!event.detail || event.detail.id !== id) return;
      window.removeEventListener("vulcan-folder-picked", onPicked);
      resolve(event.detail.path || null);
    };
    window.addEventListener("vulcan-folder-picked", onPicked);
    if (!native({ type: "pickFolder", id, start, purpose })) {
      window.removeEventListener("vulcan-folder-picked", onPicked);
      resolve(null);
    }
  });
}

/** Suggested folder to open directly: the site's, else the most recent, else the start folder. */
export async function suggestedFolder(site = null) {
  if (site && site.path) return site.path;
  try {
    const data = await get("/api/fs/recent");
    return (data.recent[0] && data.recent[0].path) || data.home.path || "~";
  } catch {
    return "~";
  }
}

function themeCards(themes, chosen) {
  const tabsByTheme = themes.inUse || {};
  return themes.list.map((theme) => {
    const used = (tabsByTheme[theme.id] || []).length;
    const status = theme.id === themes.next ? t("próximo da rotação") : used ? (used === 1 ? t("em uso em 1 aba") : t("em uso em {n} abas", { n: used })) : t("livre");
    return `<button type="button" class="nt-theme t-${esc(theme.id)} ${theme.id === chosen ? "is-on" : ""}" data-tab-theme="${esc(theme.id)}" aria-pressed="${theme.id === chosen}">
      <span class="nt-swatch"><span class="nt-prompt">❯</span> ${esc(theme.desc)}</span>
      <span class="nt-cap"><b>${esc(theme.name)}</b><span class="${theme.id === themes.next ? "is-next" : used ? "is-used" : ""}">${status}</span></span></button>`;
  }).join("");
}

/**
  * Asks for the new terminal's folder, the agent and the theme.
  * @param {{suggested?: string, site?: string}} options  suggested: absolute path or one with ~
 * @returns {Promise<{cwd: string, title: string, theme: string, agent: string}|null>}
 */
export async function askFolder({ suggested = "", site = "" } = {}) {
  let data = { home: { path: "", short: "~" }, recent: [] };
  const [recent, themes] = await Promise.all([get("/api/fs/recent").catch(() => null), loadThemes(true)]);
  if (recent) data = recent;  // no recents: the dialog keeps working with typing only
  let theme = themes.next || "homebrew";
  let agent = (themes.newTerminal && themes.newTerminal.agent) || "shell";
  const start = suggested || data.home.path || "~";
  return new Promise((resolve) => {
    const backdrop = document.createElement("div");
    backdrop.className = "dialog-backdrop";
    backdrop.innerHTML = `
      <form class="dialog folder-dialog" role="dialog" aria-modal="true" aria-labelledby="folder-title" autocomplete="off">
        <h2 id="folder-title">${t("Abrir terminal em")}</h2>
        <p class="dim folder-sub">${site ? `${t("Sessão do site {site}.", { site: `<strong>${esc(site)}</strong>` })} ` : ""}${t("Enter abre na pasta indicada.")}</p>
        <div class="folder-field">
          ${icon("folder")}
          <input name="path" class="folder-input" spellcheck="false" aria-label="${t("Pasta")}" value="${esc(start)}">
          ${hasBridge ? `<button type="button" class="btn btn-sm" data-pick>${t("Escolher…")}</button>` : ""}
        </div>
        <div class="folder-status" data-status aria-live="polite"></div>
        ${data.recent.length ? `<div class="folder-recent">
          <div class="field-label">${t("Recentes")}</div>
          <ul>${data.recent.map((r) => `<li><button type="button" class="folder-option" data-path="${esc(r.path)}">
              ${icon("folder")}<span class="folder-name">${esc(r.name)}</span><span class="folder-path">${esc(r.short)}</span>
              ${r.site ? `<span class="folder-site">${esc(r.site)}</span>` : ""}</button></li>`).join("")}</ul>
        </div>` : ""}
        <label class="field-label" for="folder-name">${t("Nome do terminal (opcional)")}</label>
        <input id="folder-name" name="title" class="input" maxlength="60" placeholder="${t("usa o nome da pasta")}">
        ${themes.list.length ? `<div class="field-label">${t("Iniciar")}</div>
        <div class="segmented nt-agents" role="radiogroup" aria-label="${t("Agente")}">${AGENTS.map(([id, label]) =>
          `<button type="button" class="seg ${id === agent ? "is-on" : ""}" data-agent="${id}" role="radio" aria-checked="${id === agent}">${label}</button>`).join("")}</div>
        <div class="field-label">${t("Tema")}</div>
        <div class="nt-themes" data-themes>${themeCards(themes, theme)}</div>
        <p class="nt-pair dim" data-pair></p>
        <label class="dialog-check nt-skip"><input type="checkbox" name="skip"><span>${t("Não perguntar a pasta da próxima vez: o botão abre direto, já no próximo tema")}</span></label>` : ""}
        <div class="dialog-actions">
          <button type="button" class="btn" data-cancel>${t("Cancelar")}</button>
          <button type="submit" class="btn btn-primary" data-ok>${icon("terminal")}<span>${t("Abrir terminal")}</span></button>
        </div>
      </form>`;
    const form = backdrop.querySelector("form");
    const input = form.elements.path;
    const pair = backdrop.querySelector("[data-pair]");
    const describe = () => {
      if (!pair) return;
      const name = (themes.byId[theme] || {}).name || theme;
      pair.innerHTML = `${icon("spark")}<span>${agent === "shell"
        ? t("A aba nasce em {name} com {session} e {theme} no ambiente.", { name: `<b>${esc(name)}</b>`, session: "<code>VULCAN_SESSION_ID</code>", theme: "<code>VULCAN_THEME</code>" })
        : t("A aba nasce em {name} com {session} e {theme} no ambiente; o terminal digita {agent} e a sessão aparece pareada em Agentes em poucos segundos.", { name: `<b>${esc(name)}</b>`, session: "<code>VULCAN_SESSION_ID</code>", theme: "<code>VULCAN_THEME</code>", agent: `<code>${agent}</code>` })}</span>`;
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
        status.textContent = t("Informe uma pasta.");
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
          status.textContent = info.exists ? t("Isso é um arquivo, não uma pasta.") : t("Pasta não encontrada.");
        }
      } catch (err) {
        if (mine !== seq) return;
        status.className = "folder-status is-error";
        status.textContent = err.message || t("Não foi possível verificar a pasta.");
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
      // the suggested theme uses up the rotation ("auto"); a hand-picked theme does not
      finish({ cwd: resolved, title: form.elements.title.value.trim(), theme: theme === themes.next ? "auto" : theme, agent });
    });
    backdrop.addEventListener("click", async (e) => {
      if (e.target === backdrop || e.target.closest("[data-cancel]")) return finish(null);
      const themeBtn = e.target.closest("[data-tab-theme]");
      if (themeBtn) {
        theme = themeBtn.dataset.tabTheme;
        backdrop.querySelectorAll("[data-tab-theme]").forEach((b) => {
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
