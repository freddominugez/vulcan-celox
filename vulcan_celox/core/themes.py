"""Temas de sessão: a aba do terminal e a sessão de agente pareada usam a mesma identidade de cor.

Temas são dados: acrescentar um é um item em THEMES e um id em ROTATION. Cada tema tem a paleta do xterm e os três
tokens da interface (--t cor viva, --t-bg fundo, --t-ink texto sobre o app). A rotação segue a ordem do Escopo 3.6
: Homebrew, Clássico (o tradicional), Oceano e Ardósia, e é lembrada entre aberturas do app.
"""

from __future__ import annotations

from typing import Dict, List, Optional

# cores ANSI comuns; cada tema troca fundo, texto, cursor e seleção
_ANSI = {
    "black": "#1f1f23", "red": "#ff6b5e", "green": "#4fd08a", "yellow": "#f2c14e", "blue": "#6aa8ff",
    "magenta": "#d38cff", "cyan": "#4fcfd6", "white": "#d4d4da", "brightBlack": "#6b6b75", "brightRed": "#ff8a7f",
    "brightGreen": "#74e0a5", "brightYellow": "#f7d67c", "brightBlue": "#92c0ff", "brightMagenta": "#e2adff",
    "brightCyan": "#7fe0e6", "brightWhite": "#f5f5f7",
}


def _theme(name: str, desc: str, accent: str, bg: str, ink: str, fg: str, selection: str) -> Dict:
    return {"name": name, "desc": desc, "accent": accent, "bg": bg, "ink": ink,
            "xterm": {**_ANSI, "background": bg, "foreground": fg, "cursor": accent, "cursorAccent": bg,
                      "selectionBackground": selection}}


THEMES: Dict[str, Dict] = {
    "homebrew": _theme("Homebrew", "âmbar sobre marrom", "#f5a524", "#2a1d12", "#f5b54a", "#f3e2c7",
                       "rgba(245, 165, 36, 0.30)"),
    "classico": _theme("Clássico", "branco sobre preto", "#d6d6dc", "#0c0c0d", "#d6d6dc", "#e8e8ea",
                       "rgba(214, 214, 220, 0.25)"),
    "oceano": _theme("Oceano", "turquesa sobre petróleo", "#2dd4bf", "#0f2a2e", "#4fdcc9", "#d8f3ef",
                     "rgba(45, 212, 191, 0.28)"),
    "ardosia": _theme("Ardósia", "lilás sobre ardósia", "#b4a5ff", "#1f2133", "#c2b6ff", "#e3e1f5",
                      "rgba(180, 165, 255, 0.28)"),
}
ROTATION: List[str] = ["homebrew", "classico", "oceano", "ardosia"]


def is_theme(value) -> bool:
    return isinstance(value, str) and value in THEMES


def css() -> str:
    """Classes .t-<id> com os tokens da interface; a página injeta este texto (CSP permite estilo inline)."""
    return "\n".join(f".t-{tid} {{ --t: {t['accent']}; --t-bg: {t['bg']}; --t-ink: {t['ink']}; }}"
                     for tid, t in THEMES.items())


def public() -> List[Dict]:
    return [{"id": tid, **THEMES[tid]} for tid in ROTATION]


class Rotation:
    """Próximo tema da rotação, guardado no Store para continuar entre aberturas do app."""

    KEY = "themes"

    def __init__(self, store):
        self.store = store

    def _index(self) -> int:
        data = self.store.load(self.KEY, {})
        value = data.get("next") if isinstance(data, dict) else 0
        return value if isinstance(value, int) and value >= 0 else 0

    def peek(self) -> str:
        return ROTATION[self._index() % len(ROTATION)]

    def take(self) -> str:
        index = self._index()
        self.store.save(self.KEY, {"next": (index + 1) % len(ROTATION)})
        return ROTATION[index % len(ROTATION)]


def theme_or_none(value) -> Optional[str]:
    return value if is_theme(value) else None
