import http.client
import json
import os
import stat
import threading
import unittest

from tests.helpers import TempDirTestCase
from tests.server_helpers import ServerTestCase
from vulcan_celox.core import server_log
from vulcan_celox.core.doctor import collect


class LogDaRotaTest(ServerTestCase):
    def setUp(self):
        super().setUp()
        from vulcan_celox.core import i18n
        self.addCleanup(i18n.set_language, i18n.language())
        i18n.set_language("pt")  # the mask mark follows the interface language
        self.addCleanup(server_log.close)
        server_log.setup(self.tmp / "dados", [self.token])

        @self.app.server.route("GET", "/api/teste/explode")
        def _boom(_req):
            raise RuntimeError(f"falhou com PASSWORD=hunter2segredo e o token {self.token}")

    def test_excecao_mascarada_e_sem_token(self):
        status, data, _ = self.request("GET", "/api/teste/explode")
        self.assertEqual(status, 500)
        path, _err = server_log.log_paths(self.tmp / "dados")
        for handler in server_log.logger().handlers:
            handler.flush()
        text = path.read_text(encoding="utf-8")
        self.assertIn("GET /api/teste/explode", text)
        self.assertIn("RuntimeError", text)
        self.assertIn("PASSWORD=[segredo]", text)
        self.assertNotIn("hunter2segredo", text)
        self.assertNotIn(self.token, text)
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)


class RotacaoTest(TempDirTestCase):
    def test_gira_com_limite_pequeno(self):
        self.addCleanup(server_log.close)
        log = server_log.setup(self.tmp, max_bytes=300, backups=3)
        for n in range(60):
            log.info("linha %03d com um texto para encher o arquivo", n)
        folder = self.tmp / server_log.LOG_DIR
        names = sorted(p.name for p in folder.iterdir())
        self.assertEqual(names, ["servidor.log", "servidor.log.1", "servidor.log.2", "servidor.log.3"])
        for path in folder.iterdir():
            self.assertLessEqual(path.stat().st_size, 400)
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertIn("linha 059", (folder / "servidor.log").read_text(encoding="utf-8"))


class ErroDoProcessoTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        from vulcan_celox.core import i18n
        self.addCleanup(i18n.set_language, i18n.language())
        i18n.set_language("pt")  # the mask mark follows the interface language

    def test_trunca_na_partida_acima_do_limite(self):
        err = server_log.prepare_error_log(self.tmp)
        err.write_text("x" * 50, encoding="utf-8")
        server_log.prepare_error_log(self.tmp, limit=100)
        self.assertEqual(err.stat().st_size, 50)
        server_log.prepare_error_log(self.tmp, limit=10)
        self.assertEqual(err.stat().st_size, 0)

    def test_ultimas_linhas_mascaradas(self):
        err = server_log.prepare_error_log(self.tmp)
        lines = [f"linha {n}" for n in range(40)] + ["Traceback (most recent call last):",
                                                     "ValueError: DB_PASSWORD=abcdef123 sk-ant-api03-abcdefghijklmnop",
                                                     "token tok" + "e" * 40]
        err.write_text("\n".join(lines) + "\n\n", encoding="utf-8")
        tail = server_log.tail(err, secrets=["tok" + "e" * 40])
        self.assertEqual(len(tail), 20)
        self.assertEqual(tail[0], "linha 23")
        self.assertEqual(tail[-2], "ValueError: DB_PASSWORD=[segredo] [segredo]")
        self.assertEqual(tail[-1], "token [token]")
        self.assertEqual(server_log.tail(self.tmp / "nao-existe.log"), [])

    def test_fluxo_mascarado(self):
        class Alvo:
            def __init__(self):
                self.parts = []

            def write(self, text):
                self.parts.append(text)

            def flush(self):
                pass

        alvo = Alvo()
        stream = server_log.MaskedStream(alvo, ["meu-token-de-sessao"])
        stream.write("API_KEY=")
        stream.write("valor123 meu-token-de-sessao\nmeio")
        stream.flush()
        self.assertEqual("".join(alvo.parts), "API_KEY=[segredo] [token]\nmeio")

    def test_doctor_mostra_os_dois_arquivos(self):
        env = {"VULCAN_CELOX_HOME": str(self.tmp / "home"), "VULCAN_LERD_BIN": str(self.tmp / "nada"),
               "VULCAN_LERD_API": "http://127.0.0.1:1", "VULCAN_VALET_BIN": str(self.tmp / "sem-valet"),
               "VULCAN_VALET_HOME": str(self.tmp / "valet"), "VULCAN_LERD_DATA": str(self.tmp / "ld")}
        logs = collect(env)["logs"]
        self.assertEqual(logs["servidor"], str(self.tmp / "home" / "logs" / "servidor.log"))
        self.assertEqual(logs["erro"], str(self.tmp / "home" / "logs" / "servidor-erro.log"))


class FilaDeConexoesTest(ServerTestCase):
    """Twelve requests at the same instant, as when a screen mounts: none is refused by the queue."""

    def test_doze_ao_mesmo_tempo(self):
        root = self.tmp / "raiz"
        root.mkdir()
        barrier = threading.Barrier(12)
        results, errors = [], []

        def one():
            try:
                conn = http.client.HTTPConnection("127.0.0.1", self.app.server.port, timeout=20)
                barrier.wait()
                conn.request("POST", "/api/files/roots", body=json.dumps({"path": str(root)}),
                             headers={"Host": f"127.0.0.1:{self.app.server.port}", "X-Vulcan-Token": self.token,
                                      "Content-Type": "application/json"})
                resp = conn.getresponse()
                resp.read()
                results.append(resp.status)
                conn.close()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=one) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 12)
        self.assertEqual(self.app.server.httpd.request_queue_size, 64)


if __name__ == "__main__":
    unittest.main()
