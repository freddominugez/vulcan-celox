import json

from tests.helpers import FIXTURES, TempDirTestCase
from tests.lerd_api_stub import LerdApiStub, closed_port_url
from vulcan_celox.core.backends import NullBackend, ValetBackend
from vulcan_celox.core.backends.lerd import LerdBackend, summarize_status
from vulcan_celox.core.runner import FakeRunner, Result


class LerdStatusTest(TempDirTestCase):
    def _backend(self, api, version_output=""):
        fake = FakeRunner()
        bin_path = str(self.tmp / "lerd")
        fake.respond([bin_path, "--version"], Result(0, version_output))
        return LerdBackend(bin_path, runner=fake, api_base=api), fake

    def test_resumo_da_api_real(self):
        with LerdApiStub() as stub:
            backend, fake = self._backend(stub.url, "lerd version 1.34.3 (commit x)\n")
            status = backend.status()
            backend.status()
        self.assertTrue(status.running)
        for trecho in ("Lerd 1.34.3", "nginx ok", "DNS .test ok", "PHP 8.5"):
            self.assertIn(trecho, status.summary)
        self.assertEqual(status.details["php_running"], ["8.5"])
        self.assertEqual(len([c for c in fake.calls if c.argv[-1] == "--version"]), 1)  # cached version

    def test_api_fora(self):
        backend, _ = self._backend(closed_port_url())
        status = backend.status()
        self.assertFalse(status.running)
        self.assertIn("Lerd parado", status.summary)

    def test_problemas_aparecem(self):
        data = json.loads((FIXTURES / "lerd-api-status.json").read_text(encoding="utf-8"))
        data["nginx"]["running"] = False
        data["dns"]["ok"] = False
        data["watcher_running"] = False
        status = summarize_status(data)
        self.assertFalse(status.running)
        for trecho in ("nginx parado", "DNS .test com problema", "watcher parado"):
            self.assertIn(trecho, status.summary)
        data["dns"]["enabled"] = False
        self.assertIn("DNS .localhost", summarize_status(data).summary)

    def test_valet_e_local(self):
        fake = FakeRunner(default=Result(0))
        valet = ValetBackend(self.tmp / "valet", runner=fake)
        self.assertEqual(valet.status().summary, "Laravel Valet · nginx rodando")
        local = NullBackend(None)
        self.assertFalse(local.status().running)
        self.assertIn("modo local", local.status().summary)
