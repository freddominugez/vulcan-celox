import unittest

from tests.helpers import FIXTURES
from vulcan_terminal.core.tables import parse_table

CHAVES = ["Site", "SSL", "URL", "Path", "PHP Version"]


class TablesTest(unittest.TestCase):
    def test_vazia(self):
        text = (FIXTURES / "valet-links-vazio.txt").read_text(encoding="utf-8")
        self.assertEqual(parse_table(text), [])

    def test_exemplo(self):
        rows = parse_table((FIXTURES / "valet-links-exemplo.txt").read_text(encoding="utf-8"))
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(list(row.keys()), CHAVES)
        self.assertEqual(rows[0]["SSL"], "X")
        self.assertEqual(rows[1]["Path"], "/Users/dev/Sites/meu blog")
        self.assertEqual(rows[2]["PHP Version"], "")

    def test_sem_tabela(self):
        self.assertEqual(parse_table(""), [])
        self.assertEqual(parse_table("Valet não está instalado."), [])

    def test_linha_com_celulas_faltando(self):
        text = "+---+---+\n| a | b |\n+---+---+\n| 1 |\n+---+---+\nfim"
        self.assertEqual(parse_table(text), [{"a": "1", "b": ""}])
