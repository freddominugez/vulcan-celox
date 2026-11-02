"""vt-06 C5: Xdebug por versão na tela Ambiente (estado, ligar com modo e sob demanda, desligar)."""

import os
from unittest import mock

from tests.helpers import FIXTURES
from tests.server_helpers import ServerTestCase
from vulcan_terminal.core.environment import parse_xdebug_status, xdebug_argv, xdebug_mode_ok
from vulcan_terminal.core.runner import Result


class ParserTest(ServerTestCase):
    def test_saida_real(self):
        # tests/fixtures/lerd-xdebug-status.txt: `lerd xdebug status` do Lerd 1.37.1 nesta máquina, Xdebug desligado
        self.assertEqual(parse_xdebug_status((FIXTURES / "lerd-xdebug-status.txt").read_text(encoding="utf-8")),
                         {"8.5": {"enabled": False, "mode": "", "on_demand": False}})

    def test_ligado_com_modo(self):
        text = "Version  Xdebug    Mode\n8.4      enabled   debug,coverage\n8.5      enabled   debug (on-demand)\n8.3  disabled\n"
        self.assertEqual(parse_xdebug_status(text), {
            "8.4": {"enabled": True, "mode": "debug,coverage", "on_demand": False},
            "8.5": {"enabled": True, "mode": "debug", "on_demand": True},
            "8.3": {"enabled": False, "mode": "", "on_demand": False}})
        self.assertEqual(parse_xdebug_status(""), {})

    def test_argv_e_modos(self):
        self.assertEqual(xdebug_argv("8.5", True, "coverage", False), ["xdebug", "on", "8.5", "--mode", "coverage"])
        self.assertEqual(xdebug_argv("8.5", True, "debug", True), ["xdebug", "on", "8.5", "--mode", "debug", "--on-demand"])
        self.assertEqual(xdebug_argv("8.4", False, "debug", True), ["xdebug", "off", "8.4"])
        for mode in ("debug", "coverage", "debug,coverage", "profile"):
            self.assertTrue(xdebug_mode_ok(mode), mode)
        for mode in ("", "debug;rm", "debug,,coverage", "--on-demand", "debug coverage", "x" * 80):
            self.assertFalse(xdebug_mode_ok(mode), mode)


class ApiTest(ServerTestCase):
    def env(self):
        env = super().env()
        lerd = self.tmp / "bin" / "lerd"
        lerd.parent.mkdir(parents=True, exist_ok=True)
        lerd.write_text("#!/bin/sh\nexit 0\n")
        os.chmod(lerd, 0o755)
        env.update({"VULCAN_LERD_BIN": str(lerd), "SHELL": "/bin/sh", "PATH": os.environ.get("PATH", "")})
        self.lerd = lerd
        return env

    def setUp(self):
        super().setUp()
        self.fake.default = Result(0, "Installed PHP versions:\n  8.4\n* 8.5\n")
        self.patch = mock.patch.object(self.app.backend, "api_get", return_value={
            "php_fpms": [{"version": "8.5", "running": True, "xdebug_enabled": True}, {"version": "8.4", "running": True}]})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.app.terminals.close_all()
        super().tearDown()

    def test_estado(self):
        self.fake.default = Result(0, "Version  Xdebug    Mode\n8.5      enabled   coverage\n8.4      disabled\n")
        data = self.request("GET", "/api/environment/xdebug")[1]
        self.assertEqual(data["port"], 9003)
        by = {v["version"]: v for v in data["versions"]}
        self.assertTrue(by["8.5"]["enabled"])
        self.assertEqual(by["8.5"]["mode"], "coverage")
        self.assertFalse(by["8.4"]["enabled"])

    def test_ligar_numa_aba(self):
        status, info, _ = self.request("POST", "/api/environment/php/8.4/xdebug",
                                       {"enabled": True, "mode": "coverage", "on_demand": True})
        self.assertEqual(status, 201, info)
        argv = " ".join(self.app.terminals.get(info["id"]).argv)
        self.assertIn(f"{self.lerd} xdebug on 8.4 --mode coverage --on-demand", argv)
        status, info, _ = self.request("POST", "/api/environment/php/8.5/xdebug", {"enabled": False})
        self.assertEqual(status, 201, info)
        self.assertIn(f"{self.lerd} xdebug off 8.5", " ".join(self.app.terminals.get(info["id"]).argv))

    def test_invalidos(self):
        self.assertEqual(self.request("POST", "/api/environment/php/8.4/xdebug", {"enabled": True, "mode": "debug;id"})[0], 400)
        self.assertEqual(self.request("POST", "/api/environment/php/8.4/xdebug", {"enabled": "sim"})[0], 400)
        self.assertEqual(self.request("POST", "/api/environment/php/8.2/xdebug", {"enabled": True})[0], 400)  # não instalada
