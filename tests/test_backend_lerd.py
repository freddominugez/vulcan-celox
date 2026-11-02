import os

from tests.helpers import TempDirTestCase
from vulcan_terminal.core.backends import LerdBackend, NullBackend, ValetBackend, detect_backend
from vulcan_terminal.core.runner import FakeRunner, Result

VERSAO_REAL = ("lerd version 1.34.3 (commit 9631ef3b6b6565dd4295ba6a7afbcb68e2b04030, "
               "built 2026-09-07T18:31:49Z)\n")


class DetectLerdTest(TempDirTestCase):
    def _bin(self, name):
        path = self.tmp / "bin" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        os.chmod(path, 0o755)
        return str(path)

    def _env(self, lerd=None, valet=None):
        return {"VULCAN_LERD_BIN": lerd or str(self.tmp / "sem-lerd"),
                "VULCAN_VALET_BIN": valet or str(self.tmp / "sem-valet"),
                "VULCAN_VALET_HOME": str(self.tmp / "valet"),
                "VULCAN_LERD_DATA": str(self.tmp / "lerd-data"),
                "VULCAN_LERD_API": "http://127.0.0.1:1"}

    def test_prioridade(self):
        lerd, valet = self._bin("lerd"), self._bin("valet")
        self.assertIsInstance(detect_backend(self._env(lerd=lerd)), LerdBackend)
        self.assertIsInstance(detect_backend(self._env(lerd=lerd, valet=valet)), LerdBackend)
        self.assertIsInstance(detect_backend(self._env(valet=valet)), ValetBackend)
        self.assertIsInstance(detect_backend(self._env()), NullBackend)

    def test_configuracao_vinda_do_ambiente(self):
        backend = detect_backend(self._env(lerd=self._bin("lerd")))
        self.assertEqual(backend.data_dir, self.tmp / "lerd-data")
        self.assertEqual(backend.dashboard_url(), "http://127.0.0.1:1/")

    def test_argv_start_stop(self):
        fake = FakeRunner()
        lerd = self._bin("lerd")
        backend = detect_backend(self._env(lerd=lerd), runner=fake)
        backend.start()
        backend.stop()
        self.assertEqual([c.argv for c in fake.calls], [(lerd, "start"), (lerd, "stop")])

    def test_restart_para_e_inicia(self):
        fake = FakeRunner()
        lerd = self._bin("lerd")
        detect_backend(self._env(lerd=lerd), runner=fake).restart()
        self.assertEqual([c.argv for c in fake.calls], [(lerd, "stop"), (lerd, "start")])

    def test_restart_nao_inicia_se_stop_falhou(self):
        lerd = self._bin("lerd")
        fake = FakeRunner()
        fake.respond([lerd, "stop"], Result(1, "", "falhou"))
        result = detect_backend(self._env(lerd=lerd), runner=fake).restart()
        self.assertEqual(result.code, 1)
        self.assertEqual([c.argv for c in fake.calls], [(lerd, "stop")])

    def test_versao(self):
        lerd = self._bin("lerd")
        fake = FakeRunner()
        fake.respond([lerd, "--version"], Result(0, VERSAO_REAL))
        self.assertEqual(detect_backend(self._env(lerd=lerd), runner=fake).version(), "1.34.3")
