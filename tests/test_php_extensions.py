"""Extensões de PHP por versão, só leitura.

`lerd-php-m-8.5.txt` e `lerd-php-ext-list-vazio.txt` são saídas reais do Lerd 1.37.1 nesta máquina (php -m no
contêiner do 8.5, por `lerd php -m` numa pasta com .php-version). `lerd-php-ext-list-docs.txt` é o exemplo da
documentação do Lerd (usage/php-extensions.md), porque aqui nenhuma extensão personalizada está declarada.
"""

import os

from tests.helpers import FIXTURES
from tests.server_helpers import ServerTestCase
from vulcan_celox.core.environment import parse_ext_list, parse_php_m
from vulcan_celox.core.runner import Result


def read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class ParserTest(ServerTestCase):
    def test_php_m_real(self):
        mods = parse_php_m(read("lerd-php-m-8.5.txt"))
        self.assertIn("redis", mods["php"])
        self.assertIn("xdebug", mods["php"])
        self.assertIn("Zend OPcache", mods["zend"])
        self.assertNotIn("[PHP Modules]", mods["php"])
        self.assertEqual(parse_php_m(""), {"php": [], "zend": []})

    def test_ext_list(self):
        self.assertEqual(parse_ext_list(read("lerd-php-ext-list-vazio.txt")), {"declared": [], "per_version": {}})
        found = parse_ext_list(read("lerd-php-ext-list-docs.txt"))
        self.assertEqual(found["declared"], ["mongodb", "swoole"])
        self.assertEqual(found["per_version"]["7.4"], "swoole (cannot load: mongodb)")
        self.assertIn("lerd php:rebuild 8.1", found["per_version"]["8.1"])


class ApiTest(ServerTestCase):
    def env(self):
        env = super().env()
        lerd = self.tmp / "bin" / "lerd"
        lerd.parent.mkdir(parents=True, exist_ok=True)
        lerd.write_text("#!/bin/sh\nexit 0\n")
        os.chmod(lerd, 0o755)
        env["VULCAN_LERD_BIN"] = str(lerd)
        return env

    def test_versao_numa_pasta_neutra(self):
        answers = {"php": Result(0, read("lerd-php-m-8.5.txt")), "php:ext": Result(0, read("lerd-php-ext-list-docs.txt"))}
        self.fake.run = lambda argv, cwd=None, env=None, timeout=60, input=None: (
            self.fake.calls.append(type("C", (), {"argv": tuple(argv), "cwd": cwd})()) or answers[argv[1]])
        data = self.request("GET", "/api/environment/php/8.4/extensions")[1]
        self.assertIn("redis", data["php"])
        self.assertEqual(data["declared"], ["mongodb", "swoole"])
        self.assertEqual(data["note"], "mongodb, swoole")
        probe = [c for c in self.fake.calls if c.argv[1:] == ("php", "-m")][0]
        with open(os.path.join(probe.cwd, ".php-version")) as fh:
            self.assertEqual(fh.read().strip(), "8.4")  # a versão vem do .php-version da pasta neutra
        self.assertEqual(self.request("GET", "/api/environment/php/9.9/extensions")[0], 400)
