// Temas de sessão: carregados uma vez do servidor (core/themes.py é a fonte), injetados como estilo
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

// Paleta do terminal quando a aba não tem tema.
export const TERMINAL_THEME = {
  background: "#0A1120",
  foreground: "#E6E9F0",
  cursor: "#B89AFF",
  cursorAccent: "#0A1120",
  selectionBackground: "rgba(184, 154, 255, 0.3)",
  black: "#1f1f23", red: "#ff6b5e", green: "#4fd08a", yellow: "#f2c14e",
  blue: "#6aa8ff", magenta: "#d38cff", cyan: "#4fcfd6", white: "#d4d4da",
  brightBlack: "#6b6b75", brightRed: "#ff8a7f", brightGreen: "#74e0a5", brightYellow: "#f7d67c",
  brightBlue: "#92c0ff", brightMagenta: "#e2adff", brightCyan: "#7fe0e6", brightWhite: "#f5f5f7",
};
