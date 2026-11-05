"""What the native Environment menu asks (/api/state): whether there is a Lerd, and the panel address it gives.
Without Lerd the shell turns the actions off and shows the notice; with it, the panel item opens that address."""

from pathlib import Path

from tests.helpers import SEM_LERD, unix_only
from tests.lerd_api_stub import LerdApiStub
from tests.server_helpers import ServerTestCase

FAKE_LERD = Path(__file__).resolve().parent / "tools" / "fake-lerd"


class SemLerdTest(ServerTestCase):
    def test_sem_lerd_nao_ha_painel(self):
        backend = self.request("GET", "/api/state")[1]["backend"]
        self.assertFalse(backend["available"])
        self.assertIsNone(backend["dashboard"])


@unix_only(SEM_LERD)
class ComLerdTest(ServerTestCase):
    def setUp(self):
        self.stub = LerdApiStub().__enter__()
        self.addCleanup(self.stub.__exit__, None, None, None)
        super().setUp()

    def env(self):
        return {**super().env(), "VULCAN_LERD_BIN": str(FAKE_LERD), "VULCAN_LERD_API": self.stub.url}

    def test_painel_no_endereco_que_o_lerd_informa(self):
        backend = self.request("GET", "/api/state")[1]["backend"]
        self.assertTrue(backend["available"])
        self.assertEqual(backend["dashboard"], self.stub.url + "/")
        self.assertNotIn("7073", backend["dashboard"])


class FonteDaCascaTest(ServerTestCase):
    def test_menu_usa_o_estado_e_nao_um_endereco_fixo(self):
        root = Path(__file__).resolve().parent.parent
        main = (root / "packaging" / "macos" / "main.swift").read_text(encoding="utf-8")
        server = (root / "packaging" / "macos" / "server.swift").read_text(encoding="utf-8")
        self.assertNotIn("127.0.0.1:7073", main)
        self.assertIn("EnvMenu.dashboard", main)
        self.assertIn("validateMenuItem", server)
