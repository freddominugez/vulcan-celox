"""vt-32 C2: arquivo novo de código não passa de 400 linhas, e os antigos desta lista não crescem (dívida registrada em
docs/pt-BR/technical-manual.md). Quem reduzir um deles baixa o número aqui."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIMIT = 400
SUFFIXES = {".py", ".mjs", ".swift", ".sh"}
FOLDERS = ("vulcan_terminal", "scripts", "tests", "packaging")
LEGACY = {
    "vulcan_terminal/web/js/terminals.mjs": 1126,
    "packaging/macos/main.swift": 687,
    "vulcan_terminal/ui/app.py": 594,
    "vulcan_terminal/web/js/views/tasks.mjs": 523,
    "vulcan_terminal/core/notebook.py": 493,
    "vulcan_terminal/core/harness.py": 462,
    "vulcan_terminal/web/js/views/site.mjs": 440,
}


def line_count(path: Path) -> int:
    with open(path, "rb") as fh:
        return sum(1 for _ in fh)


class TamanhoTest(unittest.TestCase):
    def test_limite(self):
        over = {}
        for folder in FOLDERS:
            for path in (ROOT / folder).rglob("*"):
                if path.suffix in SUFFIXES and path.is_file() and "vendor" not in path.parts and "__pycache__" not in path.parts:
                    rel = path.relative_to(ROOT).as_posix()
                    size = line_count(path)
                    if size > LEGACY.get(rel, LIMIT):
                        over[rel] = size
        self.assertEqual(over, {}, f"acima de {LIMIT} linhas (ou maior que o limite da lista): divida o arquivo")
