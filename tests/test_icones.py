"""Ícones: todo nome usado existe no sprite, e o sprite vem do Phosphor com a licença registrada."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "vulcan_terminal" / "web"
INDEX = (WEB / "index.html").read_text(encoding="utf-8")
JS = {p: p.read_text(encoding="utf-8") for p in (WEB / "js").rglob("*.mjs")}
SPRITE = set(re.findall(r'<symbol id="i-([a-z-]+)"', INDEX))


def usados():
    names = set(re.findall(r'href="#i-([a-z-]+)"', INDEX))
    for text in JS.values():
        names |= set(re.findall(r'\bicon\("([a-z-]+)"', text))
        names |= set(re.findall(r'\bicon: "([a-z-]+)"', text))
        for call in re.findall(r"\bicon\(([^()]*\?[^()]*)\)", text):  # icon(a ? "x" : "y")
            names |= set(re.findall(r'[?:]\s*"([a-z-]+)"', call))
    return names


class IconesTest(unittest.TestCase):
    def test_todo_nome_usado_existe(self):
        self.assertEqual(usados() - SPRITE, set())

    def test_todos_do_phosphor(self):
        self.assertGreaterEqual(len(SPRITE), 50)
        self.assertEqual(set(re.findall(r'<symbol id="i-[a-z-]+" viewBox="([^"]+)"', INDEX)), {"0 0 256 256"})

    def test_licenca(self):
        self.assertRegex((WEB / "vendor" / "LICENSES.md").read_text(encoding="utf-8"), r"(?m)^## @phosphor-icons/core [0-9.]+ \(MIT\)$")

    def test_tabela_do_gerador_bate_com_o_sprite(self):
        source = (ROOT / "scripts" / "gerar_icones.py").read_text(encoding="utf-8")
        tabela = source[source.index("ICONES = {"):source.index("def corpo")]
        self.assertEqual(set(re.findall(r'"([a-z-]+)": "', tabela)), SPRITE)
