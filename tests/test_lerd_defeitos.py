"""Um teste por defeito do Lerd 1.37.1 achado nas provas, contra a API falsa do Lerd.

1. `lerd dump clear` dá 403 no macOS: o app limpa pela API com `X-Lerd-CSRF` e nunca pela CLI.
2. `lerd dump status` fala em socket unix: o endereço da ponte vem só de `/api/dumps/status`.
3. Nomes dos `php.ini` de usuário: no disco `98-user.ini` e `95-shared.ini`; a documentação cita os do contêiner.
4. Exceção do Laravel como `log` de nível `error` (comportamento documentado): conta como erro.
"""

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
        # API falsa que recusa POST sem X-Lerd-CSRF, como o Lerd
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
        self.assertEqual(LerdFalso.state["cleared"], 1)  # a API falsa responde 403 sem X-Lerd-CSRF
        self.assertEqual(cli_calls(self.fake, "dump"), [])

    def test_2_endereco_da_ponte_so_pela_api(self):
        data = self.request("GET", "/api/debug/bridge")[1]
        self.assertEqual(data["addr"], "tcp:127.0.0.1:9913")
        self.assertEqual(cli_calls(self.fake, "dump"), [])  # `lerd dump status` diria unix:...lerd-dumps.sock


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
        self.assertTrue(real["path"].endswith("php/8.5/98-user.ini"))
        self.assertEqual(real["values"], {"memory_limit": "256M"})
        doc = self.request("GET", "/api/environment/php/8.4/ini")[1]
        self.assertTrue(doc["path"].endswith("php/8.4/98-lerd-user.ini"))  # só o da documentação existe: lê esse
        shared = self.request("GET", "/api/environment/php/shared/ini")[1]
        self.assertTrue(shared["path"].endswith("php/shared/95-shared.ini"))  # nenhum existe: o nome que o Lerd usa


class LogDeErroTest(TempDirTestCase):
    def test_4_log_de_nivel_error_conta_como_erro(self):
        logs = [e for e in parse_events(EVENTS) if e["kind"] == "log"]
        self.assertTrue(logs)
        self.assertTrue(all(is_error(e) for e in logs))  # eventos reais: exceções do Laravel 13 chegam assim
        info = dict(logs[0], data=dict(logs[0]["data"], level="info"))
        self.assertFalse(is_error(info))
        self.assertTrue(is_error({"kind": "exception", "data": {}}))
