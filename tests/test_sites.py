import json
import os

from tests.helpers import TempDirTestCase
from vulcan_celox.core.sites import discover_sites


class SitesTest(TempDirTestCase):
    def _arvore(self, tld=None):
        valet = self.tmp / "valet"
        (valet / "Sites").mkdir(parents=True)
        parked = self.tmp / "Code"
        for nome in ("loja", "blog", ".oculta"):
            (parked / nome).mkdir(parents=True)
        (parked / "arquivo.txt").write_text("x", encoding="utf-8")
        linked_target = self.tmp / "outros" / "api"
        linked_target.mkdir(parents=True)
        os.symlink(linked_target, valet / "Sites" / "api")
        os.symlink(self.tmp / "nao-existe", valet / "Sites" / "quebrado")
        manual = self.tmp / "manual" / "painel"
        manual.mkdir(parents=True)
        config = {"paths": [str(parked), str(valet / "Sites"), str(self.tmp / "sumiu")]}
        if tld:
            config["tld"] = tld
        (valet / "config.json").write_text(json.dumps(config), encoding="utf-8")
        return valet, {"painel": str(manual), "fantasma": str(self.tmp / "nao-ha")}

    def test_une_as_tres_fontes(self):
        valet, manual = self._arvore()
        sites = discover_sites(valet, manual)
        by_domain = {s.domain: s for s in sites}
        self.assertEqual(sorted(by_domain), ["api.test", "blog.test", "loja.test", "painel.test"])
        self.assertEqual(by_domain["api.test"].kind, "linked")
        self.assertEqual(by_domain["loja.test"].kind, "parked")
        self.assertEqual(by_domain["painel.test"].kind, "manual")
        self.assertEqual([s.kind for s in sites], ["linked", "parked", "parked", "manual"])

    def test_prioridade_no_dedupe(self):
        valet, _ = self._arvore()
        sites = discover_sites(valet, {"loja": str(self.tmp / "manual" / "painel")})
        loja = [s for s in sites if s.domain == "loja.test"]
        self.assertEqual(len(loja), 1)
        self.assertEqual(loja[0].kind, "parked")

    def test_remove_www(self):
        valet, _ = self._arvore()
        (self.tmp / "Code" / "www.vitrine").mkdir()
        domains = [s.domain for s in discover_sites(valet)]
        self.assertIn("vitrine.test", domains)
        self.assertNotIn("www.vitrine.test", domains)

    def test_tld_customizado(self):
        valet, _ = self._arvore(tld="local")
        self.assertTrue(all(s.domain.endswith(".local") for s in discover_sites(valet)))

    def test_sem_valet_so_manuais(self):
        manual = self.tmp / "m"
        manual.mkdir()
        sites = discover_sites(None, {"m": str(manual)})
        self.assertEqual([(s.name, s.kind) for s in sites], [("m", "manual")])
        self.assertEqual(discover_sites(self.tmp / "nao-existe"), [])
