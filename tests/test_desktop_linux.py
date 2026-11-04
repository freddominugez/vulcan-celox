import os
import unittest

from tests.helpers import TempDirTestCase
from vulcan_celox.desktop_linux import bootstrap_script, choose_mode, is_app_uri, main, should_exit_idle


class ChooseModeTest(unittest.TestCase):
    def which_for(self, *names):
        return lambda n: f"/usr/bin/{n}" if n in names else None

    def test_ordem_gtk_app_navegador(self):
        env = {"DISPLAY": ":0"}
        self.assertEqual(choose_mode(env, self.which_for("chromium"), gtk=lambda: "4.1"), ("gtk", "4.1"))
        self.assertEqual(choose_mode(env, self.which_for("google-chrome"), gtk=lambda: None), ("app", "/usr/bin/google-chrome"))
        self.assertEqual(choose_mode(env, self.which_for(), gtk=lambda: None), ("browser", None))
        # without a display it does not try GTK
        self.assertEqual(choose_mode({}, self.which_for("chromium"), gtk=lambda: "4.1"), ("app", "/usr/bin/chromium"))

    def test_modo_forcado(self):
        env = {"DISPLAY": ":0", "VULCAN_LINUX_MODE": "browser"}
        self.assertEqual(choose_mode(env, self.which_for("chromium"), gtk=lambda: "4.1"), ("browser", None))
        env["VULCAN_LINUX_MODE"] = "app"
        self.assertEqual(choose_mode(env, self.which_for("chromium"), gtk=lambda: "4.1"), ("app", "/usr/bin/chromium"))

    def test_ociosidade(self):
        self.assertFalse(should_exit_idle(0.0, started=100.0, now=350.0, timeout=150))  # still opening (300 s of slack)
        self.assertTrue(should_exit_idle(0.0, started=100.0, now=401.0, timeout=150))
        self.assertFalse(should_exit_idle(500.0, started=100.0, now=600.0, timeout=150))
        self.assertTrue(should_exit_idle(500.0, started=100.0, now=651.0, timeout=150))


class OrigemTest(unittest.TestCase):
    """The GTK window only navigates and only talks to the bridge on the app's origin."""

    def test_so_a_origem_do_app(self):
        self.assertTrue(is_app_uri("http://127.0.0.1:5000/#/overview", 5000))
        self.assertTrue(is_app_uri("about:blank", 5000))
        for uri in ("http://127.0.0.1:5001/", "https://127.0.0.1:5000/", "http://localhost:5000/",
                    "http://127.0.0.1.evil.com:5000/", "https://example.com/", "file:///etc/passwd",
                    "data:text/html,oi", "", None, "http://[::1"):
            with self.subTest(uri=uri):
                self.assertFalse(is_app_uri(uri, 5000))

    def test_token_so_na_pagina_do_app(self):
        script = bootstrap_script("segredo", 5000)
        self.assertTrue(script.startswith('if (location.origin === "http://127.0.0.1:5000")'))
        self.assertIn('"segredo"', script)


class CheckTest(TempDirTestCase):
    def test_check_sobe_servidor_e_sai(self):
        keys = ("VULCAN_CELOX_HOME", "VULCAN_LERD_BIN", "VULCAN_VALET_BIN", "VULCAN_KEYSTORE", "VULCAN_LERD_API")
        saved = {k: os.environ.get(k) for k in keys}
        os.environ.update({"VULCAN_CELOX_HOME": str(self.tmp / "h"), "VULCAN_LERD_BIN": str(self.tmp / "x"),
                           "VULCAN_VALET_BIN": str(self.tmp / "y"), "VULCAN_KEYSTORE": "memory",
                           "VULCAN_LERD_API": "http://127.0.0.1:1"})
        try:
            self.assertEqual(main(["--check"]), 0)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
