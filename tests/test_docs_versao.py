"""The version cited in the public documentation cannot diverge from __version__."""
import re
import unittest
from pathlib import Path

from vulcan_celox import __version__

ROOT = Path(__file__).resolve().parent.parent
PAGINAS = {
    "docs/en/README.md": r"Describes version (\d+\.\d+\.\d+)",
    "docs/pt-BR/README.md": r"Descreve a versão (\d+\.\d+\.\d+)",
    "docs/en/technical-manual.md": r"describes version (\d+\.\d+\.\d+)",
    "docs/pt-BR/technical-manual.md": r"Descreve a versão (\d+\.\d+\.\d+)",
}


class VersaoNaDocumentacaoTest(unittest.TestCase):
    def test_paginas_citam_a_versao_do_codigo(self):
        achadas = 0
        for rel, padrao in PAGINAS.items():
            page = ROOT / rel
            if not page.is_file():
                continue
            found = re.search(padrao, page.read_text(encoding="utf-8"))
            self.assertIsNotNone(found, f"{rel} deixou de citar a versão")
            self.assertEqual(found.group(1), __version__, rel)
            achadas += 1
        self.assertGreater(achadas, 0)

    def test_readme_cita_a_versao_e_o_changelog_tem_a_entrada(self):
        for rel in ("README.md", "README.pt-BR.md"):
            self.assertIn(__version__, (ROOT / rel).read_text(encoding="utf-8"), rel)
        for rel in ("CHANGELOG.md", "CHANGELOG.pt-BR.md"):
            self.assertIn(f"## [{__version__}]", (ROOT / rel).read_text(encoding="utf-8"), rel)

    def test_politica_de_seguranca_cobre_a_serie_estavel(self):
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        versoes = re.findall(r"^## \[(\d+)\.(\d+)\.\d+\]", changelog, re.M)
        serie_anterior = {f"{a}.{b}.x" for a, b in versoes}
        for rel in ("SECURITY.md", "SECURITY.pt-BR.md"):
            texto = (ROOT / rel).read_text(encoding="utf-8")
            self.assertTrue(any(s in texto for s in serie_anterior), f"{rel} não cita uma série lançada")


if __name__ == "__main__":
    unittest.main()
