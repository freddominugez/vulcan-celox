"""Logs tab of the site (storage/logs/laravel.log) and shortcuts to the Lerd logs."""

import os
from unittest import mock

from tests.helpers import TempDirTestCase, unix_only, SEM_LERD
from tests.server_helpers import ServerTestCase
from vulcan_celox.core.laravel_log import filter_entries, parse_entries, parse_laravel_line, read_log

LOG = """[2026-10-31 10:00:00] local.INFO: Usuário entrou {"id":1}
[2026-10-31 10:00:05] local.ERROR: SQLSTATE[42S02]: Base table not found {"exception":"[object] (PDOException(code: 42S02)"}
#0 /app/vendor/laravel/framework/src/Illuminate/Database/Connection.php(825): PDO->prepare()
#1 {main}
[2026-10-31 10:01:00] production.WARNING: Cache lento
[2026-10-31 10:02:00] local.DEBUG: consulta pronta
[2026-10-31 10:03:00] local.ERROR: Falhou o envio de e-mail
[2026-10-31 10:04:00] local.INFO: fim
"""


class ParserTest(TempDirTestCase):
    def test_linha(self):
        self.assertEqual(parse_laravel_line("[2026-10-31 10:01:00] production.WARNING: Cache lento"),
                         {"ts": "2026-10-31 10:01:00", "channel": "production", "level": "WARNING", "message": "Cache lento"})
        self.assertIsNone(parse_laravel_line("#0 /app/vendor/x.php(1): y()"))

    def test_stack_junta_na_entrada_anterior(self):
        entries = parse_entries(LOG.splitlines())
        self.assertEqual(len(entries), 6)
        self.assertIn("#1 {main}", entries[1]["message"])
        self.assertEqual(entries[1]["level"], "ERROR")

    def test_filtro(self):
        entries = parse_entries(LOG.splitlines())
        self.assertEqual(len(filter_entries(entries, level="ERROR")), 2)
        self.assertEqual(len(filter_entries(entries, query="cache")), 1)
        self.assertEqual(len(filter_entries(entries)), 6)

    def test_leitura_incremental(self):
        path = self.tmp / "laravel.log"
        path.write_text(LOG, encoding="utf-8")
        first = read_log(path)
        self.assertEqual(len(first["entries"]), 6)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("[2026-10-31 10:05:00] local.ERROR: novo\n[2026-10-31 10:06:00] local.INFO: linha incomple")
        more = read_log(path, first["offset"])
        self.assertEqual([e["message"] for e in more["entries"]], ["novo"])  # the line without an end is left for later
        path.write_text("[2026-10-31 11:00:00] local.INFO: girou\n", encoding="utf-8")  # rotated log
        rotated = read_log(path, more["offset"])
        self.assertTrue(rotated["reset"])
        self.assertEqual(rotated["entries"][0]["message"], "girou")

    def test_arquivo_grande_comeca_numa_linha_inteira(self):
        path = self.tmp / "laravel.log"
        line = "[2026-10-31 10:00:00] local.INFO: " + "x" * 80 + "\n"
        path.write_text(line * 2000, encoding="utf-8")  # about 230 KB
        result = read_log(path)
        self.assertTrue(result["entries"])
        self.assertTrue(all(e["message"] == "x" * 80 for e in result["entries"]))
        self.assertEqual(result["offset"], path.stat().st_size)

    def test_arquivo_ausente(self):
        result = read_log(self.tmp / "nao-existe.log")
        self.assertEqual((result["exists"], result["entries"]), (False, []))


class ApiTest(ServerTestCase):
    def env(self):
        env = super().env()
        lerd = self.tmp / "bin" / "lerd"
        lerd.parent.mkdir(parents=True, exist_ok=True)
        lerd.write_text("#!/bin/sh\nexit 0\n")
        os.chmod(lerd, 0o755)
        self.lerd = lerd
        env.update({"VULCAN_LERD_BIN": str(lerd), "SHELL": "/bin/sh", "PATH": os.environ.get("PATH", "")})
        return env

    def setUp(self):
        super().setUp()
        self.pasta = self.tmp / "loja"
        (self.pasta / "storage" / "logs").mkdir(parents=True)
        (self.pasta / "storage" / "logs" / "laravel.log").write_text(LOG, encoding="utf-8")
        row = {"name": "loja", "domain": "loja.test", "path": str(self.pasta)}
        answers = {"/api/sites": [row], "/api/services": [{"name": "mysql", "status": "active"}]}
        self.patch = mock.patch.object(self.app.backend, "api_get", side_effect=lambda p, **k: answers.get(p))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.app.terminals.close_all()
        super().tearDown()

    def test_log_do_site(self):
        data = self.request("GET", "/api/sites/loja/log")[1]
        self.assertTrue(data["exists"])
        self.assertEqual(len(data["entries"]), 6)
        again = self.request("GET", f"/api/sites/loja/log?offset={data['offset']}")[1]
        self.assertEqual(again["entries"], [])

    @unix_only(SEM_LERD)
    def test_atalhos_do_lerd(self):
        for target, args in (("php", ["logs", "-f"]), ("nginx", ["logs", "nginx", "-f"]), ("mysql", ["logs", "mysql", "-f"])):
            with self.subTest(target=target):
                status, info, _ = self.request("POST", f"/api/sites/loja/lerd-logs/{target}")
                self.assertEqual(status, 201, info)
                pty = self.app.terminals.get(info["id"])
                self.assertIn(" ".join([str(self.lerd), *args]), " ".join(pty.argv))
                self.assertEqual(pty.cwd, str(self.pasta))
        self.assertEqual(self.request("POST", "/api/sites/loja/lerd-logs/redis")[0], 404)
