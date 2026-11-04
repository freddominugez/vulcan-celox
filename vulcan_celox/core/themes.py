"""Session themes: the terminal tab and the paired agent session use the same color identity.

Themes are data: adding one is an item in THEMES and an id in ROTATION. Each theme has the xterm palette and the three
interface tokens (--t vivid color, --t-bg background, --t-ink text on the app). The rotation follows the agreed order:
Homebrew, Clássico (the traditional one), Oceano and Ardósia, and is remembered between app launches.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from vulcan_celox.core.i18n import tr

# common ANSI colors; each theme swaps background, text, cursor and selection
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
    """.t-<id> classes with the interface tokens; the page injects this text (CSP allows inline style)."""
    return "\n".join(f".t-{tid} {{ --t: {t['accent']}; --t-bg: {t['bg']}; --t-ink: {t['ink']}; }}"
                     for tid, t in THEMES.items())


def public() -> List[Dict]:
    return [{"id": tid, **THEMES[tid], "name": tr(THEMES[tid]["name"]), "desc": tr(THEMES[tid]["desc"])} for tid in ROTATION]


class Rotation:
    """Next theme in the rotation, kept in the Store to continue between app launches."""

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
