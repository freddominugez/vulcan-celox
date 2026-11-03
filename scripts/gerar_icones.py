#!/usr/bin/env python3
"""Gera o sprite de ícones em web/index.html a partir do Phosphor Icons (MIT), peso regular.

Uso: gerar_icones.py <pasta do pacote @phosphor-icons/core>. Roda à mão, só para trocar ícone ou versão. O app não tem build:
o sprite gerado fica no index.html. A tabela abaixo liga o nome usado no código ao nome no Phosphor.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

VERSAO = "2.1.1"
ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "vulcan_celox" / "web" / "index.html"
# nome no app -> arquivo em assets/regular; o sufixo -fill vem de assets/fill
ICONES = {
    "grid": "squares-four", "terminal": "terminal-window", "check-square": "check-square", "note": "note", "tag": "tag",
    "search": "magnifying-glass", "database": "database", "hex": "hexagon", "home": "house", "help": "question", "star": "star",
    "star-on": "star-fill", "plus": "plus", "x": "x", "play": "play", "stop": "stop", "restart": "arrow-clockwise",
    "external": "arrow-square-out", "split": "square-split-horizontal", "globe": "globe", "bolt": "lightning", "folder": "folder",
    "code": "code", "lock": "lock", "unlock": "lock-open", "alert": "warning", "info": "info", "check": "check", "circle": "circle",
    "circle-half": "circle-half", "circle-check": "check-circle-fill", "calendar": "calendar-blank", "trash": "trash", "pin": "push-pin",
    "grip": "dots-six-vertical", "gauge": "gauge", "chevron-right": "caret-right", "chevron-left": "caret-left",
    "chevron-down": "caret-down", "chevron-up": "caret-up", "clock": "clock", "book": "book-open", "dots": "dots-three",
    "edit": "pencil-simple", "user": "user", "columns": "columns", "list": "list", "spark": "sparkle", "branch": "git-branch",
    "tree": "tree-structure", "copy": "copy", "text": "text-align-left", "eye": "eye", "history": "clock-counter-clockwise",
    "dot": "dot-fill",
}


def corpo(pacote: Path, nome: str) -> str:
    peso = "fill" if nome.endswith("-fill") else "regular"
    svg = (pacote / "assets" / peso / f"{nome}.svg").read_text(encoding="utf-8")
    return re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1).strip()


def main() -> int:
    pacote = Path(sys.argv[1])
    linhas = [f'    <symbol id="i-{app}" viewBox="0 0 256 256">{corpo(pacote, nome)}</symbol>' for app, nome in ICONES.items()]
    html = INDEX.read_text(encoding="utf-8")
    novo, trocas = re.subn(r"<defs>.*?</defs>", lambda _: "<defs>\n" + "\n".join(linhas) + "\n  </defs>", html, count=1, flags=re.S)
    if trocas != 1:
        raise SystemExit("não achei o sprite no index.html")
    INDEX.write_text(novo, encoding="utf-8")
    print(f"{len(linhas)} ícones do Phosphor {VERSAO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
