"""vt-02 C5: favoritos no topo da barra lateral e busca por nome e domínio."""

from types import SimpleNamespace

from tests.server_helpers import ServerTestCase
from vulcan_terminal.core.site_list import arrange_sidebar


def site(name, domain=None):
    return SimpleNamespace(name=name, domain=domain or f"{name}.test")


SITES = [site("loja"), site("Blog"), site("api", "api.loja.test"), site("zeta")]


class ArrangeTest(ServerTestCase):
    def names(self, sections):
        return [(title, [s.name for s in items]) for title, items in sections]

    def test_favoritos_no_topo_sem_repetir(self):
        sections = arrange_sidebar(SITES, ["zeta", "fantasma"], "")
        self.assertEqual(self.names(sections), [("Favoritos", ["zeta"]), ("Sites", ["api", "Blog", "loja"])])

    def test_sem_favoritos_uma_secao(self):
        self.assertEqual(self.names(arrange_sidebar(SITES, [], "")), [("Sites", ["api", "Blog", "loja", "zeta"])])

    def test_busca_por_nome_e_dominio(self):
        self.assertEqual(self.names(arrange_sidebar([site("loja"), site("blog"), site("zeta")], [], "lo")),
                         [("Sites", ["blog", "loja"])])
        self.assertEqual(self.names(arrange_sidebar(SITES, ["api"], "LOJA")),
                         [("Favoritos", ["api"]), ("Sites", ["loja"])])
        self.assertEqual(arrange_sidebar(SITES, [], "nada"), [])


class FavoritoApiTest(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.app.store.save("sites", {"loja": str(self.tmp), "blog": str(self.tmp)})

    def test_marcar_e_desmarcar(self):
        status, data, _ = self.request("PUT", "/api/sites/loja/favorite", body={"favorite": True})
        self.assertEqual((status, data["favorites"]), (200, ["loja"]))
        self.assertEqual(self.request("GET", "/api/state")[1]["favorites"], ["loja"])
        self.assertEqual(self.app.store.load("favorites", []), ["loja"])
        self.request("PUT", "/api/sites/loja/favorite", body={"favorite": False})
        self.assertEqual(self.app.store.load("favorites", []), [])

    def test_entradas_invalidas(self):
        self.assertEqual(self.request("PUT", "/api/sites/fantasma/favorite", body={"favorite": True})[0], 404)
        self.assertEqual(self.request("PUT", "/api/sites/loja/favorite", body={"favorite": "sim"})[0], 400)
