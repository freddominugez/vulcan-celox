"""vt-04 C3: abas de processo longo (servidor de desenvolvimento, fila, logs, túnel)."""

import os

from tests.server_helpers import ServerTestCase
from vulcan_terminal.core.quick_commands import is_long_running

LONGOS = ["npm run dev", "php artisan serve", "php artisan queue:work --tries=3", "php artisan reverb:start",
          "php artisan horizon", "lerd logs -f", "/opt/homebrew/bin/lerd share loja --cloudflare", "pnpm dev",
          "tail -f storage/logs/laravel.log"]
COMUNS = ["git log", "php -v", "composer install", "npm run build", "php artisan migrate", "lerd logs", "", None]


class ClassificaTest(ServerTestCase):
    def test_tabela(self):
        for command in LONGOS:
            with self.subTest(command=command):
                self.assertTrue(is_long_running(command))
        for command in COMUNS:
            with self.subTest(command=command):
                self.assertFalse(is_long_running(command))


class TerminaisTest(ServerTestCase):
    def env(self):
        env = super().env()
        env.update({"SHELL": "/bin/sh", "PATH": os.environ.get("PATH", "")})
        return env

    def tearDown(self):
        self.app.terminals.close_all()
        super().tearDown()

    def test_marca_na_lista_e_no_aviso_de_fechar(self):
        longo = self.request("POST", "/api/terminals", body={"command": "tail -f /dev/null", "cwd": str(self.tmp)})[1]
        comum = self.request("POST", "/api/terminals", body={"cwd": str(self.tmp)})[1]
        infos = {t["id"]: t for t in self.request("GET", "/api/terminals")[1]["terminals"]}
        self.assertTrue(infos[longo["id"]]["long_running"])
        self.assertFalse(infos[comum["id"]]["long_running"])
        self.assertEqual(infos[longo["id"]]["command"], "tail -f /dev/null")
        busy = self.request("GET", f"/api/terminals/{longo['id']}/busy")[1]
        self.assertTrue(busy["long_running"])
        self.assertEqual(busy["command"], "tail -f /dev/null")
