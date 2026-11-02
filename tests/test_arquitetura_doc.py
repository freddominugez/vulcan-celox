"""O manual técnico, nas duas línguas, cita todo módulo do servidor e do núcleo."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ArquiteturaDocTest(unittest.TestCase):
    def test_todo_modulo_citado(self):
        doc = "\n".join((ROOT / "docs" / lang / "technical-manual.md").read_text(encoding="utf-8") for lang in ("en", "pt-BR"))
        missing = []
        for folder in ("server", "core"):
            for path in sorted((ROOT / "vulcan_terminal" / folder).rglob("*.py")):
                if path.name == "__init__.py":
                    continue
                if path.stem not in doc:
                    missing.append(str(path.relative_to(ROOT)))
        self.assertEqual(missing, [], "módulos sem menção no manual técnico")
