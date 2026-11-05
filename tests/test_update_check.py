import json
import time

from tests.server_helpers import ServerTestCase
from tests.helpers import TempDirTestCase
from vulcan_celox import __version__
from vulcan_celox.core.ai import AiError
from vulcan_celox.core.runner import FakeRunner, Result
from vulcan_celox.core.update_check import API_PATH, RELEASE_PREFIX, fetch_latest, is_newer

GOOD = {"tag_name": "v99.0.0", "html_url": RELEASE_PREFIX + "tag/v99.0.0"}


def answer(status, body):
    return lambda *_a: (status, json.dumps(body).encode())


class VersionTest(TempDirTestCase):
    def test_compara_numeros(self):
        self.assertTrue(is_newer("1.10.0", "1.9.9"))
        self.assertTrue(is_newer("v2.0.0", "1.9.9"))
        self.assertFalse(is_newer("1.2.1", "1.2.1"))
        self.assertFalse(is_newer("1.2.0", "1.2.1"))
        self.assertFalse(is_newer("1.3.0-test", "1.2.1"))
        self.assertFalse(is_newer(None, "1.2.1"))


class FetchTest(TempDirTestCase):
    env = {"VULCAN_GH_BIN": "/bin/gh"}

    def test_anonimo_nao_chama_gh(self):
        runner = FakeRunner()
        self.assertEqual(fetch_latest(self.env, runner, "1", answer(200, GOOD))["latest"], "99.0.0")
        self.assertEqual(runner.calls, [])

    def test_privado_usa_gh(self):
        runner = FakeRunner()
        runner.respond(["/bin/gh", "api", API_PATH], Result(0, json.dumps(GOOD)))
        self.assertEqual(fetch_latest(self.env, runner, "1", answer(404, {}))["url"], GOOD["html_url"])

    def test_privado_sem_gh(self):
        self.assertEqual(fetch_latest({"VULCAN_GH_BIN": ""}, FakeRunner(), "1", answer(404, {})), {"reason": "unavailable"})
        runner = FakeRunner(default=Result(1, "", "HTTP 404"))
        self.assertEqual(fetch_latest(self.env, runner, "1", answer(404, {})), {"reason": "unavailable"})

    def test_sem_rede(self):
        def offline(*_a):
            raise AiError("sem conexão")
        runner = FakeRunner()
        self.assertEqual(fetch_latest(self.env, runner, "1", offline), {"reason": "offline"})
        self.assertEqual(runner.calls, [])

    def test_link_de_outro_lugar_e_recusado(self):
        for url in ("https://evil.example/x", "http://github.com/freddominugez/vulcan-celox/releases/x", "https://github.com/outro/repo/releases/x", None):
            found = fetch_latest(self.env, FakeRunner(), "1", answer(200, {"tag_name": "v9.0.0", "html_url": url}))
            self.assertEqual(found, {"reason": "invalid"}, url)
        self.assertEqual(fetch_latest(self.env, FakeRunner(), "1", answer(200, {"tag_name": "x", "html_url": GOOD["html_url"]})), {"reason": "invalid"})


class ApiTest(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.calls = 0

        def transport(*_a):
            self.calls += 1
            return 200, json.dumps(GOOD).encode()
        self.app.update_transport = transport

    def get(self, path="/api/update"):
        status, data = self.request("GET", path)[:2]
        self.assertEqual(status, 200)
        return data

    def test_consulta_uma_vez_por_dia(self):
        first = self.get()
        self.assertTrue(first["newer"])
        self.assertEqual(first["current"], __version__)
        self.get()
        self.assertEqual(self.calls, 1)
        data = self.app.store.load("update_check", {})
        data["checked_at"] = time.time() - 25 * 3600
        self.app.store.save("update_check", data)
        self.get()
        self.assertEqual(self.calls, 2)

    def test_desligado_nao_consulta(self):
        self.request("PUT", "/api/update", {"enabled": False})
        self.assertFalse(self.get()["enabled"])
        self.assertEqual(self.calls, 0)

    def test_verificar_agora_ignora_o_intervalo(self):
        self.get()
        status, data = self.request("POST", "/api/update/check", {})[:2]
        self.assertEqual(status, 200)
        self.assertEqual(self.calls, 2)
        self.assertTrue(data["newer"])

    def test_ambiente_desligado_nunca_consulta(self):
        self.app.env["VULCAN_UPDATE_CHECK"] = "0"
        self.assertFalse(self.get()["enabled"])
        self.assertEqual(self.request("POST", "/api/update/check", {})[0], 409)
        self.assertEqual(self.calls, 0)

    def test_falha_guarda_o_que_ja_se_sabia(self):
        self.get()
        self.app.update_transport = answer(500, {})
        self.app.env["VULCAN_GH_BIN"] = ""
        data = self.request("POST", "/api/update/check", {})[1]
        self.assertEqual(data["reason"], "unavailable")
        self.assertEqual(data["latest"], "99.0.0")

    def test_aviso_dispensado_fica_guardado(self):
        self.get()
        self.assertEqual(self.request("PUT", "/api/update", {"dismissed": "99.0.0"})[1]["dismissed"], "99.0.0")
        self.assertEqual(self.request("PUT", "/api/update", {"enabled": "sim"})[0], 400)
