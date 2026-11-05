// Quick open of the Code screen: the list comes from the disk photo the server already has. Names are data: always through esc.

import { get } from "../../api.mjs";
import { esc } from "../../dom.mjs";
import { t } from "../../i18n.mjs";

const SHOWN = 100;

/** Letters in order, in the name first. Smaller is better; null if it does not match. */
export function scorePath(rel, text) {
  if (!text) return 0;
  const path = rel.toLowerCase();
  const wanted = text.toLowerCase();
  const name = path.slice(path.lastIndexOf("/") + 1);
  const direct = name.indexOf(wanted);
  if (direct >= 0) return direct;
  const whole = path.indexOf(wanted);
  if (whole >= 0) return 100 + whole;
  let at = -1;
  let gaps = 0;
  for (const ch of wanted) {
    const next = path.indexOf(ch, at + 1);
    if (next < 0) return null;
    if (at >= 0) gaps += next - at - 1;
    at = next;
  }
  return 1000 + gaps;
}

export function filterPaths(files, text, max = SHOWN) {
  const scored = [];
  for (const rel of files) {
    const score = scorePath(rel, text);
    if (score !== null) scored.push([score, rel.length, rel]);
  }
  scored.sort((a, b) => a[0] - b[0] || a[1] - b[1] || (a[2] < b[2] ? -1 : 1));
  return scored.slice(0, max).map((r) => r[2]);
}

export async function openQuickOpen(root, pick) {
  if (document.querySelector(".ce-quick")) return;
  const before = document.activeElement;
  const back = document.createElement("div");
  back.className = "ce-quick-back";
  const box = document.createElement("div");
  box.className = "ce-quick";
  box.setAttribute("role", "dialog");
  box.setAttribute("aria-modal", "true");
  box.setAttribute("aria-label", t("Ir para arquivo"));
  box.innerHTML = `<input type="text" spellcheck="false" autocomplete="off" placeholder="${t("Nome do arquivo")}" aria-label="${t("Nome do arquivo")}" role="combobox" aria-expanded="true" aria-controls="ce-quick-list">
    <div class="ce-quick-list" id="ce-quick-list" role="listbox"><p class="ce-quick-note">${t("Carregando…")}</p></div>`;
  document.body.append(back, box);
  const input = box.querySelector("input");
  const list = box.querySelector(".ce-quick-list");
  input.focus();
  let files = [];
  let partial = false;
  let shown = [];
  let at = 0;
  const close = () => {
    back.remove();
    box.remove();
    if (before && before.isConnected && before.focus) before.focus();
  };
  const choose = (rel) => {
    close();
    pick(rel);
  };
  const draw = () => {
    shown = filterPaths(files, input.value);
    at = Math.min(at, Math.max(0, shown.length - 1));
    list.innerHTML = shown.length
      ? shown.map((rel, i) => `<button type="button" class="ce-quick-item ${i === at ? "is-on" : ""}" role="option" aria-selected="${i === at}" data-rel="${esc(rel)}" title="${esc(rel)}">${esc(rel)}</button>`).join("")
        + (partial ? `<p class="ce-quick-note">${t("Pasta grande: a lista só tem as pastas abertas.")}</p>` : "")
      : `<p class="ce-quick-note">${t("Nenhum arquivo com esse nome.")}</p>`;
    const on = list.querySelector(".is-on");
    if (on && on.scrollIntoView) on.scrollIntoView({ block: "nearest" });
  };
  input.addEventListener("input", () => {
    at = 0;
    draw();
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      close();
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      at = Math.max(0, Math.min(shown.length - 1, at + (e.key === "ArrowDown" ? 1 : -1)));
      draw();
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (shown[at]) choose(shown[at]);
    }
  });
  back.addEventListener("pointerdown", close);
  list.addEventListener("click", (e) => {
    const item = e.target.closest("[data-rel]");
    if (item) choose(item.dataset.rel);
  });
  try {
    const data = await get(`/api/files/photo?root=${encodeURIComponent(root)}`);
    if (!box.isConnected) return;
    files = data.files;
    partial = data.partial;
    draw();
  } catch (_) {
    list.innerHTML = `<p class="ce-quick-note">${t("Não foi possível listar os arquivos.")}</p>`;
  }
}
