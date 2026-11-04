import unittest
from pathlib import Path

from tests.helpers import unix_only
from vulcan_celox.core.keychain import SecretToolStore, default_keystore, KeychainStore
from vulcan_celox.core.oscompat import default_data_dir, default_shell, is_macos, open_argv
from vulcan_celox.core.runner import FakeRunner, Result

KEY = "sk-ant-api03-" + "q1W2e3" * 8  # synthetic


class PlatformTest(unittest.TestCase):
    @unix_only("no Windows o shell padrão é o PowerShell (tests/test_windows.py)")
    def test_shell_padrao(self):
        exists = lambda p: p in {"/bin/bash", "/bin/sh", "/opt/fish"}
        self.assertEqual(default_shell({"SHELL": "/opt/fish"}, exists), "/opt/fish")
        self.assertEqual(default_shell({"SHELL": "/bin/zsh"}, exists), "/bin/bash")  # zsh absent
        self.assertEqual(default_shell({}, lambda p: False), "/bin/sh")

    def test_pasta_de_dados(self):
        self.assertEqual(default_data_dir({"HOME": "/Users/dev"}, "darwin"),
                         Path("/Users/dev/Library/Application Support/VulcanCelox"))
        self.assertEqual(default_data_dir({"HOME": "/home/dev"}, "linux"), Path("/home/dev/.local/share/vulcan-celox"))
        self.assertEqual(default_data_dir({"HOME": "/home/dev", "XDG_DATA_HOME": "/dados"}, "linux"),
                         Path("/dados/vulcan-celox"))

    def test_abrir(self):
        which = lambda name: {"xdg-open": "/usr/bin/xdg-open", "code": "/usr/bin/code"}.get(name)
        self.assertEqual(open_argv("url", "http://a.test", {}, "darwin"), ["/usr/bin/open", "http://a.test"])
        self.assertEqual(open_argv("editor", "/p", {}, "darwin"), ["/usr/bin/open", "-t", "/p"])
        self.assertEqual(open_argv("editor", "/p", {"VULCAN_EDITOR": "Cursor"}, "darwin"), ["/usr/bin/open", "-a", "Cursor", "/p"])
        self.assertEqual(open_argv("url", "http://a.test", {}, "linux", which), ["/usr/bin/xdg-open", "http://a.test"])
        self.assertEqual(open_argv("folder", "/p", {}, "linux", which), ["/usr/bin/xdg-open", "/p"])
        self.assertEqual(open_argv("editor", "/p", {}, "linux", which), ["/usr/bin/code", "/p"])
        self.assertEqual(open_argv("editor", "/p", {}, "linux", lambda n: None), ["xdg-open", "/p"])
        self.assertTrue(is_macos("darwin"))
        self.assertFalse(is_macos("linux"))


class SecretToolTest(unittest.TestCase):
    def test_valor_so_pelo_stdin(self):
        runner = FakeRunner()
        store = SecretToolStore(runner=runner, tool="/usr/bin/secret-tool")
        runner.respond(["/usr/bin/secret-tool", "lookup", "service", store.service, "account", "api-key"], Result(0, KEY))
        store.set(KEY)
        self.assertEqual(runner.calls[0].argv[:2], ("/usr/bin/secret-tool", "store"))
        self.assertEqual(runner.calls[0].input, KEY)
        for call in runner.calls:
            self.assertNotIn(KEY, " ".join(call.argv))
        self.assertEqual(store.get(), KEY)
        store.delete()
        self.assertEqual(runner.calls[-1].argv[1], "clear")

    def test_sem_secret_tool(self):
        store = SecretToolStore(runner=FakeRunner(), tool=None)
        store.tool = None
        self.assertIsNone(store.get())
        with self.assertRaises(Exception) as ctx:
            store.set(KEY)
        self.assertIn("libsecret-tools", str(ctx.exception))

    def test_escolha_por_sistema(self):
        self.assertIsInstance(default_keystore(FakeRunner(), "darwin"), KeychainStore)
        self.assertIsInstance(default_keystore(FakeRunner(), "linux"), SecretToolStore)
