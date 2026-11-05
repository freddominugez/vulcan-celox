"""JSON that is valid but of the wrong shape does not stop the app from opening."""

import json

from tests.helpers import TempDirTestCase
from tests.server_helpers import ServerTestCase
from vulcan_celox.core.runner import FakeRunner
from vulcan_celox.server.app import VulcanApp


class FormaErradaTest(TempDirTestCase):
    def env(self):
        return {"VULCAN_CELOX_HOME": str(self.tmp / "home"), "VULCAN_LEGACY_HOME": str(self.tmp / "legacy"), "VULCAN_VALET_HOME": str(self.tmp / "valet"),
                "VULCAN_VALET_BIN": str(self.tmp / "sem-valet"), "VULCAN_LERD_BIN": str(self.tmp / "sem-lerd"), "VULCAN_LERD_DATA": str(self.tmp / "lerd"),
                "VULCAN_LERD_API": "http://127.0.0.1:1", "HOME": str(self.tmp), "VULCAN_LANGUAGE": "pt", "VULCAN_UPDATE_CHECK": "0"}

    def opens_with(self, name, value):
        home = self.tmp / "home"
        home.mkdir(exist_ok=True)
        (home / f"{name}.json").write_text(json.dumps(value), encoding="utf-8")
        app = VulcanApp(env=self.env(), runner=FakeRunner(), token="token-de-teste-123")
        app.data_lock.release()
        return app

    def test_migrations_lista(self):
        self.opens_with("migrations", [])

    def test_migrations_texto(self):
        self.opens_with("migrations", "x")

    def test_sessoes_com_id_numerico(self):
        self.opens_with("terminal_sessions", [{"id": 5, "title": "x"}])

    def test_sessoes_nao_lista(self):
        self.opens_with("terminal_sessions", {"a": 1})

    def test_sessoes_com_campos_tortos(self):
        self.opens_with("terminal_sessions", [{"id": "abc", "tags": 3, "commands": "x"}])


class VersaoTest(ServerTestCase):
    def test_data_invalida_nao_da_erro(self):
        self.app.store.save("update_check", {"checked_at": "ontem", "latest": "1.0.0"})
        self.assertEqual(self.request("GET", "/api/update")[0], 200)
