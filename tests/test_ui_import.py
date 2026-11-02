"""A camada ui só pode depender de vulcan_terminal e da biblioteca padrão."""

import ast
import importlib.util
import os
import sysconfig
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parent.parent / "vulcan_terminal" / "ui"
STDLIB = os.path.realpath(sysconfig.get_paths()["stdlib"])


def _is_stdlib(module: str) -> bool:
    if module == "__future__":
        return True
    spec = importlib.util.find_spec(module)
    if spec is None:
        return False
    origin = spec.origin or ""
    if origin in ("built-in", "frozen") or not origin:
        return True
    origin = os.path.realpath(origin)
    return origin.startswith(STDLIB) and "site-packages" not in origin


class UiImportTest(unittest.TestCase):
    def test_imports_permitidos(self):
        files = sorted(UI.glob("*.py"))
        self.assertTrue(files)
        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    roots = [node.module.split(".")[0]]
                else:
                    continue
                for root in roots:
                    self.assertTrue(root == "vulcan_terminal" or _is_stdlib(root),
                                    f"{path.name} importa {root}")
