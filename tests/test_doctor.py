import json
import os
import subprocess
import sys
from pathlib import Path

from tests.helpers import TempDirTestCase
from tests.lerd_api_stub import LerdApiStub, closed_port_url
from vulcan_terminal.core.doctor import collect

ROOT = Path(__file__).resolve().parent.parent


class DoctorTest(TempDirTestCase):
    def _fake_lerd(self):
        path = self.tmp / "lerd"
        path.write_text('#!/bin/sh\necho "lerd version 1.34.3 (commit teste)"\n', encoding="utf-8")
        os.chmod(path, 0o755)
        return str(path)

    def _env(self, api, lerd=None):
        return {"VULCAN_TERMINAL_HOME": str(self.tmp / "home"), "VULCAN_LERD_BIN": lerd or str(self.tmp / "nada"),
                "VULCAN_LERD_DATA": str(self.tmp / "lerd-data"), "VULCAN_LERD_API": api,
                "VULCAN_VALET_BIN": str(self.tmp / "sem-valet"), "VULCAN_VALET_HOME": str(self.tmp / "valet")}

    def test_precos_invalidos_avisam(self):
        # vt-22 C2: precos.json inválido mantém o padrão e aparece no --doctor
        home = self.tmp / "home"
        home.mkdir()
        (home / "precos.json").write_text("{", encoding="utf-8")
        data = collect(self._env(closed_port_url()))
        self.assertIn("JSON inválido", data["precos"]["aviso"])
        self.assertEqual((data["precos"]["moeda"], data["precos"]["conferido_em"]), ("USD", "2026-11-01"))

    def test_lerd_rodando(self):
        with LerdApiStub() as stub:
            data = collect(self._env(stub.url, self._fake_lerd()))
        self.assertEqual((data["backend"], data["backend_version"], data["running"]), ("lerd", "1.34.3", True))
        self.assertIn("vulcan-demo.test", [s["domain"] for s in data["sites"]])
        self.assertTrue(data["dashboard"].startswith("http://127.0.0.1:"))

    def test_modo_local(self):
        data = collect(self._env(closed_port_url()))
        self.assertEqual((data["backend"], data["running"], data["sites"]), ("local", False, []))

    def test_cli_imprime_json_e_sai_zero(self):
        env = dict(os.environ, **self._env(closed_port_url(), self._fake_lerd()), PYTHONPATH=str(ROOT))
        proc = subprocess.run([sys.executable, "-m", "vulcan_terminal", "--doctor"], env=env,
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["backend"], "lerd")
        self.assertFalse(data["running"])
        self.assertIn("Lerd 1.34.3 parado", data["summary"])
