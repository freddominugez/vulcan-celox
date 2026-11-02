"""vt-04 C2: comandos do projeto em um clique, a partir do que existe na pasta, mais os do usuário."""

import json
import os
from unittest import mock

from tests.helpers import TempDirTestCase
from tests.server_helpers import ServerTestCase
from vulcan_terminal.core.quick_commands import project_commands


class ListaTest(TempDirTestCase):
    def commands(self, lerd=False, custom=()):
        return [c["command"] for c in project_commands(str(self.tmp), lerd=lerd, custom=list(custom))]

    def test_so_composer(self):
        (self.tmp / "composer.json").write_text("{}")
        self.assertEqual(self.commands(), ["git status -sb", "composer install"])

    def test_laravel_com_package_json_e_lerd(self):
        (self.tmp / "artisan").write_text("<?php")
        (self.tmp / "package.json").write_text(json.dumps({"scripts": {"dev": "vite", "build": "vite build", "lint": "eslint ."}}))
        found = self.commands(lerd=True)
        self.assertEqual(len(found), 11, found)
        for expected in ("php artisan about", "php artisan route:list", "php artisan migrate:status", "php artisan test",
                         "lerd db:shell", "npm run dev", "npm run build", "npm run lint", "lerd logs -f", "lerd site:doctor"):
            self.assertIn(expected, found)

    def test_no_maximo_oito_scripts(self):
        (self.tmp / "package.json").write_text(json.dumps({"scripts": {f"s{i}": "x" for i in range(12)}}))
        self.assertEqual(len([c for c in self.commands() if c.startswith("npm run")]), 8)

    def test_package_json_invalido_nao_quebra(self):
        (self.tmp / "package.json").write_text("{nao")
        self.assertEqual(self.commands(), ["git status -sb"])
        (self.tmp / "package.json").write_text(json.dumps({"scripts": ["nao", "e", "objeto"]}))
        self.assertEqual(self.commands(), ["git status -sb"])

    def test_comando_proprio_no_fim(self):
        found = project_commands(str(self.tmp), custom=[{"label": "fila", "command": "php artisan queue:work"}])
        self.assertEqual(found[-1], {"label": "fila", "command": "php artisan queue:work", "custom": True})


class ApiTest(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.pasta = self.tmp / "loja"
        self.pasta.mkdir()
        (self.pasta / "composer.json").write_text("{}")
        self.app.store.save("sites", {"loja": str(self.pasta)})

    def test_lista_adiciona_e_remove(self):
        base = "/api/sites/loja/commands"
        self.assertEqual([c["command"] for c in self.request("GET", base)[1]["commands"]],
                         ["git status -sb", "composer install"])
        status, data, _ = self.request("POST", base, body={"label": "fila", "command": "php artisan queue:work"})
        self.assertEqual(status, 201, data)
        self.assertEqual(data["commands"][-1]["command"], "php artisan queue:work")
        status, data, _ = self.request("DELETE", f"{base}?command=php%20artisan%20queue:work")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["commands"]), 2)

    def test_entradas_invalidas(self):
        base = "/api/sites/loja/commands"
        self.assertEqual(self.request("POST", base, body={"label": "x", "command": ""})[0], 400)
        self.assertEqual(self.request("POST", base, body={"label": "x", "command": "a" * 600})[0], 400)
        self.assertEqual(self.request("GET", "/api/sites/fantasma/commands")[0], 404)
