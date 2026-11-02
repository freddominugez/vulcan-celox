import shutil

from tests.helpers import FIXTURES, TempDirTestCase
from tests.lerd_api_stub import LerdApiStub, closed_port_url
from vulcan_terminal.core.backends.lerd import LerdBackend, site_from_row


class LerdSitesTest(TempDirTestCase):
    def _backend(self, api, with_yaml=True):
        data = self.tmp / "lerd"
        data.mkdir(exist_ok=True)
        if with_yaml:
            shutil.copy(FIXTURES / "lerd-sites.yaml", data / "sites.yaml")
        return LerdBackend(self.tmp / "lerd-bin", data_dir=data, api_base=api)

    def test_via_api(self):
        with LerdApiStub() as stub:
            sites = self._backend(stub.url, with_yaml=False).list_sites()
        by_name = {s.name: s for s in sites}
        self.assertEqual(sorted(by_name), ["loja", "vulcan-demo"])
        demo, loja = by_name["vulcan-demo"], by_name["loja"]
        self.assertEqual((demo.domain, demo.php, demo.node, demo.secured), ("vulcan-demo.test", "8.5", "22", False))
        self.assertEqual(demo.url, "http://vulcan-demo.test")
        self.assertEqual((loja.secured, loja.url, loja.php), (True, "https://loja.test", "8.3"))
        self.assertTrue(all(s.kind == "lerd" for s in sites))

    def test_api_fora_usa_sites_yaml(self):
        sites = self._backend(closed_port_url()).list_sites()
        by_name = {s.name: s for s in sites}
        self.assertEqual(sorted(by_name), ["legado", "loja", "vulcan-demo"])
        self.assertEqual(by_name["legado"].domain, "legado.test")
        self.assertEqual(by_name["legado"].path, "/Users/dev/Code/sistema legado")
        self.assertEqual(by_name["loja"].url, "https://loja.test")

    def test_manual_nao_duplica_e_soma(self):
        pasta = self.tmp / "vulcan-demo"
        pasta.mkdir()
        extra = self.tmp / "extra"
        extra.mkdir()
        sites = self._backend(closed_port_url()).list_sites({"vulcan-demo": str(pasta), "extra": str(extra)})
        domains = [s.domain for s in sites]
        self.assertEqual(domains.count("vulcan-demo.test"), 1)
        self.assertEqual(next(s for s in sites if s.domain == "vulcan-demo.test").kind, "lerd")
        self.assertEqual(sites[-1].kind, "manual")

    def test_sem_registro(self):
        extra = self.tmp / "extra"
        extra.mkdir()
        sites = self._backend(closed_port_url(), with_yaml=False).list_sites({"extra": str(extra)})
        self.assertEqual([(s.name, s.kind) for s in sites], [("extra", "manual")])

    def test_registro_invalido(self):
        self.assertIsNone(site_from_row({"name": "x"}))
        self.assertIsNone(site_from_row({"domains": ["a.test"]}))
