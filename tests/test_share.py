"""Sharing the site through a tunnel in a tab and finding the public URL in the output.

The outputs below are illustrative (tool format), not captures: opening a real public tunnel
exposes the user's site on the internet and has no place in the tests.
"""

import os
import shlex
from unittest import mock

from tests.helpers import unix_only, SEM_LERD
from tests.server_helpers import ServerTestCase
from tests.test_pty import wait_for
from vulcan_celox.server.sites_api import extract_public_url

NGROK = """\x1b[1mngrok\x1b[0m                                                       (Ctrl+C to quit)
Session Status                online
Web Interface                 http://127.0.0.1:4040
Forwarding                    https://ab12-187-10-3-4.ngrok-free.app -> https://loja.test:443
"""
CLOUDFLARE = """2026-10-31T10:00:00Z INF Requesting new quick Tunnel on trycloudflare.com...
2026-10-31T10:00:02Z INF +--------------------------------------------------------------------------------------------+
2026-10-31T10:00:02Z INF |  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |
2026-10-31T10:00:02Z INF |  https://quiet-river-light-1234.trycloudflare.com                                          |
"""
LOCALHOST_RUN = "Connect to http://localhost:3000\n7c1f3a2b9d.lhr.life tunneled with tls termination, https://7c1f3a2b9d.lhr.life\n"
SEM_URL = "Get ngrok at https://ngrok.com/download\nOpening https://loja.test in your browser\n"


class ExtrairTest(ServerTestCase):
    def test_ferramentas(self):
        self.assertEqual(extract_public_url(NGROK), "https://ab12-187-10-3-4.ngrok-free.app")
        self.assertEqual(extract_public_url(CLOUDFLARE), "https://quiet-river-light-1234.trycloudflare.com")
        self.assertEqual(extract_public_url(LOCALHOST_RUN), "https://7c1f3a2b9d.lhr.life")

    def test_ignora_enderecos_que_nao_sao_o_tunel(self):
        self.assertIsNone(extract_public_url(SEM_URL))
        self.assertIsNone(extract_public_url(""))


class CompartilharApiTest(ServerTestCase):
    def env(self):
        env = super().env()
        self.lerd = self.tmp / "bin" / "lerd"
        self.lerd.parent.mkdir(parents=True, exist_ok=True)
        # a fake "lerd share" that prints the tunnel URL and keeps running, like the real one
        self.lerd.write_text("#!/bin/sh\necho 'Forwarding https://ab12.ngrok-free.app -> http://loja.test'\nsleep 30\n")
        os.chmod(self.lerd, 0o755)
        env.update({"VULCAN_LERD_BIN": str(self.lerd), "SHELL": "/bin/sh", "PATH": os.environ.get("PATH", "")})
        return env

    def setUp(self):
        super().setUp()
        self.pasta = self.tmp / "loja"
        self.pasta.mkdir()
        row = {"name": "loja", "domain": "loja.test", "path": str(self.pasta), "tls": False}
        self.patch = mock.patch.object(self.app.backend, "api_get", side_effect=lambda p, **k: [row] if p == "/api/sites" else {})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.app.terminals.close_all()
        super().tearDown()

    @unix_only(SEM_LERD)
    def test_aba_com_o_share_e_url_publica(self):
        status, info, _ = self.request("POST", "/api/sites/loja/share", body={"tool": "cloudflare"})
        self.assertEqual(status, 201, info)
        pty = self.app.terminals.get(info["id"])
        self.assertIn(shlex.join([str(self.lerd), "share", "loja", "--cloudflare"]), " ".join(pty.argv))
        self.assertTrue(wait_for(lambda: self.request("GET", f"/api/terminals/{info['id']}/public-url")[1]["url"]))
        self.assertEqual(self.request("GET", f"/api/terminals/{info['id']}/public-url")[1]["url"],
                         "https://ab12.ngrok-free.app")
        self.request("DELETE", f"/api/terminals/{info['id']}")  # closing the tab ends the tunnel
        self.assertFalse(pty.alive)

    def test_ferramenta_invalida(self):
        self.assertEqual(self.request("POST", "/api/sites/loja/share", body={"tool": "outra"})[0], 400)
        self.assertEqual(self.request("GET", "/api/terminals/abc999/public-url")[0], 404)
