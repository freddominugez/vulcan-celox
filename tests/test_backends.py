import json
import os
import re
from pathlib import Path

from tests.helpers import TempDirTestCase, unix_only, MODOS
from vulcan_celox.core.backends import NullBackend, ValetBackend, detect_backend
from vulcan_celox.core.runner import FakeRunner, Result

PKG = Path(__file__).resolve().parent.parent / "vulcan_celox"


class DetectTest(TempDirTestCase):
    def _bin(self, executable=True):
        path = self.tmp / "bin" / "valet"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\necho Valet\n", encoding="utf-8")
        os.chmod(path, 0o755 if executable else 0o644)
        return path

    def _env(self, bin_path):
        return {"VULCAN_VALET_BIN": str(bin_path), "VULCAN_VALET_HOME": str(self.tmp / "valet"),
                "VULCAN_LERD_BIN": str(self.tmp / "sem-lerd")}

    def test_valet_presente(self):
        backend = detect_backend(self._env(self._bin()))
        self.assertIsInstance(backend, ValetBackend)
        self.assertTrue(backend.available)

    @unix_only(MODOS)
    def test_nao_executavel_vira_null(self):
        self.assertIsInstance(detect_backend(self._env(self._bin(executable=False))), NullBackend)

    def test_ausente_vira_null(self):
        backend = detect_backend(self._env(self.tmp / "nada"))
        self.assertIsInstance(backend, NullBackend)
        self.assertFalse(backend.available)
        self.assertEqual(backend.restart().code, 1)

    def test_argv_de_servicos(self):
        fake = FakeRunner()
        backend = detect_backend(self._env(self._bin()), runner=fake)
        backend.restart()
        backend.start()
        backend.stop()
        b = str(self.tmp / "bin" / "valet")
        self.assertEqual([c.argv for c in fake.calls], [(b, "restart"), (b, "start"), (b, "stop")])

    def test_nginx_running_via_pgrep(self):
        fake = FakeRunner(default=Result(1))
        backend = detect_backend(self._env(self.tmp / "nada"), runner=fake)
        self.assertFalse(backend.nginx_running())
        self.assertEqual(fake.calls[0].argv, ("/usr/bin/pgrep", "-x", "nginx"))

    def test_list_sites_usa_valet_home(self):
        valet = self.tmp / "valet"
        (self.tmp / "Code" / "loja").mkdir(parents=True)
        valet.mkdir()
        (valet / "config.json").write_text(json.dumps({"paths": [str(self.tmp / "Code")]}),
                                           encoding="utf-8")
        self.assertEqual([s.domain for s in detect_backend(self._env(self._bin())).list_sites()],
                         ["loja.test"])
        # without Valet: config ignored, only manual ones
        self.assertEqual(detect_backend(self._env(self.tmp / "nada")).list_sites(), [])

    def test_acoes_de_site_implementadas(self):
        # what used to be "available from now on" now calls the CLI (table in test_backends_sites)
        fake = FakeRunner()
        backend = detect_backend(self._env(self._bin()), runner=fake)
        self.assertTrue(backend.secure("loja").ok)
        self.assertEqual(list(fake.calls[-1].argv)[1:], ["secure", "loja"])


class SemHerdTest(TempDirTestCase):
    def test_pacote_nao_menciona_herd(self):
        for path in PKG.rglob("*.py"):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                code = line.split("#", 1)[0]
                self.assertIsNone(re.search(r"\bherd\b", code, re.IGNORECASE),
                                  f"{path.relative_to(PKG)}:{n} menciona herd")
