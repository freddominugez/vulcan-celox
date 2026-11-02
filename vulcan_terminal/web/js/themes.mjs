// Temas de sessão (vt-18 C1): carregados uma vez do servidor (core/themes.py é a fonte), injetados como estilo
// e aplicados a cada terminal pelo tema da aba. Sem tema, o terminal usa a paleta padrão do app.

import { get } from "./api.mjs";

let loaded = null;
export const themes = { list: [], byId: {}, next: null, inUse: {}, newTerminal: { skip_folder: false, agent: "shell" } };

export function loadThemes(force = false) {
  if (loaded && !force) return loaded;
  loaded = get("/api/themes").then((data) => {
    themes.list = data.themes;
    themes.byId = Object.fromEntries(data.themes.map((t) => [t.id, t]));
    themes.next = data.next;
    themes.inUse = data.in_use;
    themes.newTerminal = data.new_terminal || themes.newTerminal;
    let style = document.getElementById("vt-themes");
    if (!style) {
      style = document.createElement("style");
      style.id = "vt-themes";
      document.head.appendChild(style);
    }
    style.textContent = data.css;
    window.dispatchEvent(new CustomEvent("vulcan-themes-loaded"));
    return themes;
  }).catch(() => {
    loaded = null;  // tenta de novo na próxima chamada
    return themes;
  });
  return loaded;
}

/** Paleta do xterm para o tema, ou null (o terminal fica com a paleta padrão). */
export function xtermTheme(id) {
  const t = id && themes.byId[id];
  return t ? t.xterm : null;
}
