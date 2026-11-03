// Adicionar site: linkar uma pasta com um domínio ou parkear uma pasta de projetos, pelo backend.

import { get, hasBridge, post } from "./api.mjs";
import { esc, icon, toast } from "./dom.mjs";
import { pickNative } from "./folder-dialog.mjs";

const DOMAIN = /^[a-z0-9-]+$/;

function suggest(name) {
  let s = (name.split("/").filter(Boolean).pop() || "").toLowerCase();
  if (s.startsWith("www.")) s = s.slice(4);
  if (s.endsWith(".test")) s = s.slice(0, -5);
  return s.replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "");
}

export function addSiteDialog({ backend = null, onDone = () => {} } = {}) {
  const available = Boolean(backend && backend.available);
  // só o Lerd escreve no projeto ao registrar (.php-version); o Valet só cria o link
  const note = !available ? `${icon("text")}<span>Sem Lerd ou Valet: instale um dos dois para adicionar sites.</span>`
    : backend.name === "lerd" ? `${icon("text")}<span>O Lerd grava <code>.php-version</code> na pasta do projeto ao registrar o site.</span>` : "";
  const backdrop = document.createElement("div");
  backdrop.className = "dialog-backdrop";
  backdrop.innerHTML = `
    <form class="dialog site-add" role="dialog" aria-modal="true" aria-labelledby="site-add-title" autocomplete="off">
      <h2 id="site-add-title">Adicionar site</h2>
      <div class="segmented" role="radiogroup" aria-label="Como adicionar">
        <button type="button" class="seg is-on" data-kind="link" role="radio" aria-checked="true">Linkar pasta</button>
        <button type="button" class="seg" data-kind="park" role="radio" aria-checked="false">Parkear pasta</button>
      </div>
      <p class="dim site-add-sub" data-sub></p>
      <div class="folder-field">
        ${icon("folder")}
        <input name="path" class="folder-input" spellcheck="false" aria-label="Pasta" placeholder="/Users/voce/Code/projeto">
        ${hasBridge ? `<button type="button" class="btn btn-sm" data-pick>Escolher…</button>` : ""}
      </div>
      <label class="field-label" for="site-domain" data-domain-label>Domínio</label>
      <div class="site-add-domain" data-domain-row>
        <input id="site-domain" name="domain" class="input" spellcheck="false" aria-describedby="site-add-status"><span class="dim">.test</span>
      </div>
      <div class="folder-status" id="site-add-status" data-status aria-live="polite"></div>
      ${note ? `<p class="site-add-note dim">${note}</p>` : ""}
      <pre class="site-add-output" data-output hidden></pre>
      <div class="dialog-actions">
        <button type="button" class="btn" data-cancel>Cancelar</button>
        <button type="submit" class="btn btn-primary" data-ok ${available ? "" : "disabled"}>${icon("plus")}<span>Adicionar</span></button>
      </div>
    </form>`;
  document.body.appendChild(backdrop);
  const form = backdrop.querySelector("form");
  const { path, domain } = form.elements;
  const status = backdrop.querySelector("[data-status]");
  const output = backdrop.querySelector("[data-output]");
  let kind = "link";
  let edited = false;

  const describe = () => {
    backdrop.querySelector("[data-sub]").textContent = kind === "link"
      ? "Registra esta pasta como um site, no domínio escolhido."
      : "Cada subpasta com um projeto PHP vira um site, inclusive as que você criar depois.";
    backdrop.querySelector("[data-domain-row]").hidden = kind !== "link";
    backdrop.querySelector("[data-domain-label]").hidden = kind !== "link";
  };
  const validate = () => {
    if (kind !== "link") return true;
    const value = domain.value.trim();
    if (DOMAIN.test(value) && !value.startsWith("-")) {
      status.className = "folder-status is-ok";
      status.innerHTML = `${icon("check")}<span>${esc(value)}.test</span>`;
      return true;
    }
    const better = suggest(value);
    status.className = "folder-status is-error";
    status.innerHTML = `<span>Só letras minúsculas, números e hífen, sem <code>.test</code>.</span>${
      better ? ` <button type="button" class="link-btn" data-use="${esc(better)}">Usar ${esc(better)}</button>` : ""}`;
    return false;
  };
  const close = () => backdrop.remove();

  backdrop.addEventListener("click", async (event) => {
    const seg = event.target.closest("[data-kind]");
    if (seg) {
      kind = seg.dataset.kind;
      backdrop.querySelectorAll("[data-kind]").forEach((b) => {
        b.classList.toggle("is-on", b === seg);
        b.setAttribute("aria-checked", String(b === seg));
      });
      describe();
      validate();
    }
    if (event.target.closest("[data-pick]")) {
      const picked = await pickNative(path.value || "~");
      if (picked) {
        path.value = picked;
        if (!edited) domain.value = suggest(picked);
        validate();
      }
    }
    const use = event.target.closest("[data-use]");
    if (use) {
      domain.value = use.dataset.use;
      validate();
    }
    if (event.target.closest("[data-cancel]") || event.target === backdrop) close();
  });
  path.addEventListener("input", () => {
    if (!edited) domain.value = suggest(path.value);
    validate();
  });
  domain.addEventListener("input", () => {
    edited = true;
    validate();
  });
  backdrop.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!available || !validate()) return;
    const ok = backdrop.querySelector("[data-ok]");
    ok.disabled = true;
    output.hidden = true;
    try {
      const result = await post("/api/sites", { kind, path: path.value.trim(), domain: domain.value.trim() });
      if (result.ok) {
        close();
        toast(kind === "link" ? `Site ${domain.value.trim()}.test adicionado.` : "Pasta parkeada.", { kind: "ok" });
        onDone();
      } else {
        output.hidden = false;
        output.textContent = result.output || `o backend respondeu com código ${result.code}`;
      }
    } catch (err) {
      status.className = "folder-status is-error";
      status.textContent = err.message;
      if (err.status === 400 && /domínio/.test(err.message)) validate();
    } finally {
      ok.disabled = false;
    }
  });
  describe();
  path.focus();
  get("/api/fs/recent").then((data) => {
    if (!path.value && data && data.home) path.placeholder = `${data.home.path}/Code/projeto`;
  }).catch(() => {});
}
