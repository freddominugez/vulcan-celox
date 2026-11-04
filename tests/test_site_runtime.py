"""The tab's PHP and Node match the site's (lerd which) and a warning when the tab does not use the Lerd shims."""

import os
from unittest import mock

from tests.helpers import FIXTURES, unix_only, SEM_LERD
from tests.server_helpers import ServerTestCase
from vulcan_celox.core.runner import Result
from vulcan_celox.core.site_runtime import parse_php_version, parse_which, shim_status


class ParserTest(ServerTestCase):
    def test_lerd_which_real(self):
        info = parse_which((FIXTURES / "lerd-which.txt").read_text(encoding="utf-8"))
        self.assertEqual(info, {"site": "loja.test", "php": "8.5", "node": "22", "docroot": "/Users/dev/Code/loja/public",
                                "nginx": "/Users/dev/.local/share/lerd/nginx/conf.d/loja.test.conf"})

    def test_site_nao_registrado(self):
        self.assertEqual(parse_which(" ✗ no site registered for /tmp — link it first with lerd link\n"), {})

    def test_php_v(self):
        self.assertEqual(parse_php_version("PHP 8.3.12 (cli) (built: Sep 24 2026)\nCopyright (c) The PHP Group"), "8.3.12")
        self.assertEqual(parse_php_version("zsh: command not found: php"), "")

    @unix_only(SEM_LERD)
    def test_shims(self):
        home = self.tmp
        shims = home / ".local" / "share" / "lerd" / "bin"
        shims.mkdir(parents=True)
        other = self.tmp / "brew"
        other.mkdir()
        for folder in (shims, other):
            (folder / "php").write_text("#!/bin/sh\n")
            os.chmod(folder / "php", 0o755)
        ok = shim_status(f"{shims}:{other}", str(home))
        self.assertTrue(ok["ok"])
        bad = shim_status(f"{other}:{shims}", str(home))
        self.assertFalse(bad["ok"])
        self.assertIn("não é o do Lerd", bad["warning"])
        none = shim_status(str(other), str(home))
        self.assertIn("path:enable", none["warning"])


class RuntimeApiTest(ServerTestCase):
    def env(self):
        env = super().env()
        lerd = self.tmp / "bin" / "lerd"
        lerd.parent.mkdir(parents=True, exist_ok=True)
        lerd.write_text("#!/bin/sh\nexit 0\n")
        os.chmod(lerd, 0o755)
        env["VULCAN_LERD_BIN"] = str(lerd)
        return env

    def setUp(self):
        super().setUp()
        self.pasta = self.tmp / "loja"
        self.pasta.mkdir()
        row = {"name": "loja", "domain": "loja.test", "path": str(self.pasta)}
        self.patch = mock.patch.object(self.app.backend, "api_get", side_effect=lambda p, **k: [row] if p == "/api/sites" else {})
        self.patch.start()
        self.fake.default = Result(0, (FIXTURES / "lerd-which.txt").read_text(encoding="utf-8"))

    def tearDown(self):
        self.patch.stop()
        super().tearDown()

    def test_runtime_do_site_com_cache(self):
        data = self.request("GET", "/api/sites/loja/runtime")[1]
        self.assertEqual((data["php"], data["node"]), ("8.5", "22"))
        self.assertIn("shim", data)
        which = [c for c in self.fake.calls if list(c.argv)[1:] == ["which"]]
        self.assertEqual(len(which), 1)
        self.assertEqual(which[0].cwd, str(self.pasta))
        self.request("GET", "/api/sites/loja/runtime")
        self.assertEqual(len([c for c in self.fake.calls if list(c.argv)[1:] == ["which"]]), 1)  # cache
        self.assertEqual(self.request("GET", "/api/sites/fantasma/runtime")[0], 404)
