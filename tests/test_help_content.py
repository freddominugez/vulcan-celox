"""Help content in a single place, no em dash, with enough FAQ and images that exist."""

import json
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "vulcan_celox" / "web"
DATA = json.loads((WEB / "help" / "conteudo.json").read_text(encoding="utf-8"))


class HelpContentTest(unittest.TestCase):
    def test_sem_travessao(self):
        text = (WEB / "help" / "conteudo.json").read_text(encoding="utf-8")
        self.assertNotIn("—", text)
        self.assertNotIn("–", text)

    def test_faq_e_secoes(self):
        self.assertGreaterEqual(len(DATA["faq"]), 15)
        ids = [s["id"] for s in DATA["secoes"]]
        self.assertEqual(len(ids), len(set(ids)))
        for wanted in ("primeiros-passos", "projetos-php", "lerd", "node", "terminais", "agentes", "custo",
                       "prompts", "harness", "atalhos", "seguranca"):
            self.assertIn(wanted, ids)
        for f in DATA["faq"]:
            self.assertTrue(f["q"].endswith("?") or f["q"].endswith("."), f["q"])
            self.assertIn(f.get("secao"), ids)

    def test_imagens_existem(self):
        for s in DATA["secoes"]:
            for b in s["blocos"]:
                if "img" in b:
                    path = WEB / "img" / "manual" / b["img"]
                    self.assertTrue(path.is_file(), path)
                    self.assertGreater(path.stat().st_size, 20000)
                    self.assertTrue(b.get("alt"))
