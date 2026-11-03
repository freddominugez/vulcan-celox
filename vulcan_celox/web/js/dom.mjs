// Utilitários de DOM: escape, ícones, toasts, debounce e formatação.

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ESCAPES[c]);
}

export function icon(name, cls = "") {
  return `<svg class="i ${cls}" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
}

export function $(selector, root = document) {
  return root.querySelector(selector);
}

export function $$(selector, root = document) {
  return Array.from(root.querySelectorAll(selector));
}

export function debounce(fn, ms) {
  let timer = null;
  const wrapped = (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
  wrapped.flush = (...args) => {
    clearTimeout(timer);
    fn(...args);
  };
  return wrapped;
}

let toastTimer = null;
export function toast(message, { kind = "info", action = null, timeout = 4000 } = {}) {
  const region = document.getElementById("toasts");
  region.innerHTML = `
    <div class="toast toast-${kind}" role="status">
      ${icon(kind === "error" ? "alert" : kind === "ok" ? "check" : "info")}
      <span>${esc(message)}</span>
      ${action ? `<button class="btn btn-ghost btn-sm" data-toast-action>${esc(action.label)}</button>` : ""}
    </div>`;
  if (action) {
    region.querySelector("[data-toast-action]").addEventListener("click", () => {
      region.innerHTML = "";
      action.run();
    });
  }
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (region.innerHTML = ""), timeout);
}

export function reportError(err) {
  toast(err && err.message ? err.message : String(err), { kind: "error", timeout: 6000 });
}

/** Rola até o item aberto pela árvore da barra lateral e o destaca por um instante (uma vez por abertura). */
export function flashFocus(root, options, selector) {
  if (!options.focus) return null;
  const el = root.querySelector(selector(CSS.escape(options.focus)));
  if (!el) return null;
  options.focus = null;
  el.scrollIntoView({ block: "center" });
  el.classList.add("is-flash");
  setTimeout(() => el.classList.remove("is-flash"), 1800);
  return el;
}

export function todayISO() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function formatDue(due) {
  if (!due) return "";
  const [y, m, d] = due.split("-");
  const months = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const sameYear = Number(y) === new Date().getFullYear();
  return `${Number(d)} ${months[Number(m) - 1]}${sameYear ? "" : ` ${y}`}`;
}

export function shortPath(path) {
  if (!path) return "";
  const home = /^\/Users\/[^/]+/.exec(path);
  return home ? `~${path.slice(home[0].length)}` : path;
}

export function progressBar(progress, cls = "") {
  const pct = progress ? progress.pct : 0;
  return `<span class="bar ${cls}" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100">
    <span class="bar-fill" style="transform:scaleX(${pct / 100})"></span></span>`;
}
