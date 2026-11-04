import threading
from unittest import mock

from tests.helpers import TempDirTestCase
from tests.server_helpers import ServerTestCase
from vulcan_celox.core.backends.base import EnvStatus
from vulcan_celox.core.runner import Result
from vulcan_celox.core.store import Store
from vulcan_celox.server.autostart import EnvAutostart, failure_reason


class FakeBackend:
    label = "Lerd"

    def __init__(self, running=False, start_code=0, comes_up=True, available=True):
        self.available = available
        self.running = running
        self.start_code = start_code
        self.comes_up = comes_up
        self.starts = 0

    def status(self):
        return EnvStatus(self.running, "")

    def start(self):
        self.starts += 1
        if self.start_code == 0 and self.comes_up:
            self.running = True
        return Result(self.start_code, " → dns\n → nginx\n", "erro: podman parado\n" if self.start_code else "")


class FakeApp:
    def __init__(self, tmp, backend, env=None):
        self.backend = backend
        self.env = env or {}
        self.store = Store(tmp)
        self._service_lock = threading.Lock()


class EnvAutostartTest(TempDirTestCase):
    def auto(self, backend, env=None):
        auto = EnvAutostart(FakeApp(self.tmp, backend, env))
        auto.set_enabled(True)
        auto.start_wait = 0
        return auto

    def test_parado_inicia(self):
        backend = FakeBackend(running=False)
        auto = self.auto(backend)
        self.assertEqual(auto.run(), "ready")
        self.assertEqual((backend.starts, auto.state()["message"]), (1, "Lerd iniciado"))

    def test_desligado_ate_o_usuario_escolher(self):
        """Lerd is optional: with no choice recorded, opening the app starts nothing."""
        backend = FakeBackend(running=False)
        auto = EnvAutostart(FakeApp(self.tmp, backend))
        self.assertFalse(auto.enabled())
        self.assertEqual((auto.run(), backend.starts), ("skipped", 0))

    def test_espera_o_ambiente_responder_depois_do_comando(self):
        """`lerd start` returns while the VM and the panel still come up: that is not a failure."""
        backend = FakeBackend(running=False, comes_up=False)
        answers = iter([False, False, True])
        backend.status = lambda: EnvStatus(next(answers, True), "")
        from vulcan_celox.server import autostart as module
        auto = self.auto(backend)
        auto.start_wait = 30
        with mock.patch.object(module, "POLL_SECONDS", 0):
            self.assertEqual(auto.run(), "ready")

    def test_linha_de_sucesso_nunca_vira_motivo(self):
        ok_lines = " → nginx\n → starting lerd-tray… ✓\n"
        self.assertEqual(failure_reason(Result(1, ok_lines, "")), "código 1")
        self.assertEqual(failure_reason(Result(1, ok_lines, "Error: unable to connect\n")), "Error: unable to connect")
        backend = FakeBackend(running=False, comes_up=False)
        backend.start = lambda: Result(0, ok_lines, "")
        auto = self.auto(backend)
        self.assertEqual(auto.run(), "failed")
        self.assertNotIn("lerd-tray", auto.state()["message"])
        self.assertIn("não respondeu", auto.state()["message"])

    def test_ja_rodando_nao_inicia(self):
        backend = FakeBackend(running=True)
        self.assertEqual(self.auto(backend).run(), "ready")
        self.assertEqual(backend.starts, 0)

    def test_falha_explica(self):
        auto = self.auto(FakeBackend(start_code=1))
        self.assertEqual(auto.run(), "failed")
        self.assertIn("podman parado", auto.state()["message"])
        auto = self.auto(FakeBackend(start_code=0, comes_up=False))
        self.assertEqual(auto.run(), "failed")

    def test_desligado_por_preferencia_env_ou_sem_ambiente(self):
        backend = FakeBackend()
        auto = self.auto(backend)
        auto.set_enabled(False)
        self.assertEqual((auto.run(), backend.starts), ("skipped", 0))
        self.assertFalse(EnvAutostart(FakeApp(self.tmp, backend)).state()["enabled"])
        self.assertEqual(self.auto(FakeBackend(), env={"VULCAN_AUTOSTART": "0"}).run(), "skipped")
        self.assertEqual(self.auto(FakeBackend(available=False)).run(), "skipped")

    def test_espera_outra_operacao_de_servico(self):
        backend = FakeBackend()
        app = FakeApp(self.tmp, backend)
        auto = EnvAutostart(app)
        auto.set_enabled(True)
        app._service_lock.acquire()
        thread = auto.begin()
        thread.join(0.3)
        self.assertEqual(backend.starts, 0)
        app._service_lock.release()
        thread.join(2)
        self.assertEqual(backend.starts, 1)


class AutostartApiTest(ServerTestCase):
    def test_estado_e_preferencia(self):
        auto = self.request("GET", "/api/state")[1]["autostart"]
        self.assertEqual((auto["phase"], auto["enabled"]), ("idle", False))
        self.assertFalse(self.request("PATCH", "/api/preferences", body={"autostart_env": False})[1]["autostart"]["enabled"])
        self.assertFalse(self.request("GET", "/api/state")[1]["autostart"]["enabled"])
        self.assertEqual(self.request("PATCH", "/api/preferences", body={"autostart_env": "sim"})[0], 400)
