"""One test per Lerd 1.37.1 defect found in the proofs, against the fake Lerd API.

1. `lerd dump clear` gives 403 on macOS: the app clears through the API with `X-Lerd-CSRF` and never through the CLI.
2. `lerd dump status` speaks on a unix socket: the bridge address comes only from `/api/dumps/status`.
3. Names of the user `php.ini` files: on disk `98-user.ini` and `95-shared.ini`; the documentation cites the container ones.
4. Laravel exception as a `log` of level `error` (documented behavior): counts as an error.
"""

from pathlib import Path
import http.server
import json
import os
import threading

from tests.helpers import FIXTURES, TempDirTestCase
from tests.server_helpers import ServerTestCase
from tests.test_lerd_dumps import LerdFalso
from vulcan_celox.core.lerd_dumps import is_error, parse_events

EVENTS = json.loads((FIXTURES / "lerd-api-dumps.json").read_text(encoding="utf-8"))


def cli_calls(fake, word):
    return [c for c in fake.calls if word in list(c.argv)[1:]]


def fake_lerd_bin(tmp):
    lerd = tmp / "bin" / "lerd"
    lerd.parent.mkdir(parents=True, exist_ok=True)
    lerd.write_text("#!/bin/sh\nexit 0\n")
    os.chmod(lerd, 0o755)
    return str(lerd)


class DumpsPelaApiTest(ServerTestCase):
    def env(self):
        # fake API that refuses POST without X-Lerd-CSRF, like Lerd
        self.lerd_srv = http.server.HTTPServer(("127.0.0.1", 0), LerdFalso)
        threading.Thread(target=self.lerd_srv.serve_forever, daemon=True).start()
        LerdFalso.state.update(enabled=False, cleared=0, queries=[])
        env = super().env()
        env.update({"VULCAN_LERD_BIN": fake_lerd_bin(self.tmp),
                    "VULCAN_LERD_API": f"http://127.0.0.1:{self.lerd_srv.server_port}"})
        return env

    def tearDown(self):
        super().tearDown()
        self.lerd_srv.shutdown()
        self.lerd_srv.server_close()

    def test_1_limpar_pela_api_com_o_cabecalho_nunca_pela_cli(self):
        status, data, _ = self.request("POST", "/api/debug/clear")
        self.assertEqual(status, 200, data)
        self.assertEqual(LerdFalso.state["cleared"], 1)  # the fake API answers 403 without X-Lerd-CSRF
        self.assertEqual(cli_calls(self.fake, "dump"), [])

    def test_2_endereco_da_ponte_so_pela_api(self):
        data = self.request("GET", "/api/debug/bridge")[1]
        self.assertEqual(data["addr"], "tcp:127.0.0.1:9913")
        self.assertEqual(cli_calls(self.fake, "dump"), [])  # `lerd dump status` would say unix:...lerd-dumps.sock


class PhpIniNomesTest(ServerTestCase):
    def env(self):
        env = super().env()
        lerd = fake_lerd_bin(self.tmp)
        self.data = self.tmp / "lerd-data"
        for folder in ("8.5", "8.4", "shared"):
            (self.data / "php" / folder).mkdir(parents=True)
        (self.data / "php" / "8.5" / "98-user.ini").write_text("memory_limit = 256M\n", encoding="utf-8")
        (self.data / "php" / "8.4" / "98-lerd-user.ini").write_text("memory_limit = 64M\n", encoding="utf-8")
        env.update({"VULCAN_LERD_BIN": lerd, "VULCAN_LERD_DATA": str(self.data)})
        return env

    def test_3_nome_real_e_nome_da_documentacao(self):
        real = self.request("GET", "/api/environment/php/8.5/ini")[1]
        self.assertTrue(Path(real["path"]).as_posix().endswith("php/8.5/98-user.ini"))
        self.assertEqual(real["values"], {"memory_limit": "256M"})
        doc = self.request("GET", "/api/environment/php/8.4/ini")[1]
        self.assertTrue(Path(doc["path"]).as_posix().endswith("php/8.4/98-lerd-user.ini"))  # only the documented one exists: reads that one
        shared = self.request("GET", "/api/environment/php/shared/ini")[1]
        self.assertTrue(Path(shared["path"]).as_posix().endswith("php/shared/95-shared.ini"))  # none exists: the name Lerd uses


class LogDeErroTest(TempDirTestCase):
    def test_4_log_de_nivel_error_conta_como_erro(self):
        logs = [e for e in parse_events(EVENTS) if e["kind"] == "log"]
        self.assertTrue(logs)
        self.assertTrue(all(is_error(e) for e in logs))  # real events: Laravel 13 exceptions arrive like this
        info = dict(logs[0], data=dict(logs[0]["data"], level="info"))
        self.assertFalse(is_error(info))
        self.assertTrue(is_error({"kind": "exception", "data": {}}))
