"""Documentação pública nas duas línguas, com links internos válidos."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARES = ("README", "CONTRIBUTING", "CODE_OF_CONDUCT", "SECURITY", "CHANGELOG", "ROADMAP")
LINK = re.compile(r"\]\(([^)\s]+)\)")


def paginas():
    for nome in PARES:
        yield ROOT / f"{nome}.md"
        yield ROOT / f"{nome}.pt-BR.md"
    yield from sorted((ROOT / "docs" / "en").glob("*.md"))
    yield from sorted((ROOT / "docs" / "pt-BR").glob("*.md"))


class DocsAbertosTest(unittest.TestCase):
    def test_arquivos_padrao(self):
        self.assertIn("MIT License", (ROOT / "LICENSE").read_text(encoding="utf-8"))
        for rel in ("bug_report.yml", "feature_request.yml", "config.yml"):
            self.assertTrue((ROOT / ".github" / "ISSUE_TEMPLATE" / rel).is_file(), rel)
        self.assertTrue((ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md").is_file())

    def test_mesmas_paginas_nas_duas_linguas(self):
        en = {p.name for p in (ROOT / "docs" / "en").glob("*.md")}
        pt = {p.name for p in (ROOT / "docs" / "pt-BR").glob("*.md")}
        self.assertEqual(en, pt - {"guia-detalhado.md"})

    def test_links_internos_existem(self):
        faltando = []
        for page in paginas():
            for alvo in LINK.findall(page.read_text(encoding="utf-8")):
                if alvo.startswith(("http://", "https://", "#", "mailto:")):
                    continue
                if not (page.parent / alvo.split("#", 1)[0]).exists():
                    faltando.append(f"{page.relative_to(ROOT)}: {alvo}")
        self.assertEqual(faltando, [])

    def test_sem_travessao(self):
        for page in paginas():
            self.assertNotIn("—", page.read_text(encoding="utf-8"), str(page))
