"""A new code file does not exceed 400 lines, and the old ones on this list do not grow (debt recorded in
docs/pt-BR/technical-manual.md). Whoever shrinks one of them lowers the number here."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIMIT = 400
SUFFIXES = {".py", ".mjs", ".swift", ".sh"}
FOLDERS = ("vulcan_celox", "scripts", "tests", "packaging")
LEGACY = {
    "packaging/macos/main.swift": 577,
    "vulcan_celox/ui/app.py": 594,
    "vulcan_celox/web/js/views/tasks.mjs": 523,
    "vulcan_celox/core/notebook.py": 493,
    "vulcan_celox/core/harness.py": 462,
    "vulcan_celox/web/js/views/site.mjs": 434,
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
