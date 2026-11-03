"""Ações de site no Lerd e no Valet, por argv em lista e pasta de trabalho."""

import json
from pathlib import Path
from unittest import mock

from tests.helpers import FIXTURES, TempDirTestCase
from vulcan_terminal.core.backends import LerdBackend, NullBackend, ValetBackend
from vulcan_terminal.core.runner import FakeRunner, Result

LERD = "/opt/homebrew/bin/lerd"
VALET = "/Users/dev/.composer/vendor/bin/valet"
LOJA = "/Users/dev/Code/loja"

# (método, argumentos, argv depois do binário, cwd)
LERD_TABLE = [
    ("link", (LOJA, "loja"), ["link", "loja"], LOJA),
    ("link", (LOJA, ""), ["link"], LOJA),
    ("unlink", ("loja",), ["unlink", "loja"], None),
    ("park", ("/Users/dev/Code",), ["park", "/Users/dev/Code"], None),
    ("unpark", ("/Users/dev/Code",), ["unpark", "/Users/dev/Code"], None),
    ("secure", ("loja",), ["secure", "loja"], None),
    ("unsecure", ("loja",), ["unsecure", "loja"], None),
    ("isolate", (LOJA, "8.4"), ["isolate", "8.4"], LOJA),
    ("isolate_node", (LOJA, "22"), ["isolate:node", "22"], LOJA),
]
VALET_TABLE = [
    ("link", (LOJA, "loja"), ["link", "loja"], LOJA),
    ("unlink", ("loja",), ["unlink", "loja"], None),
    ("park", ("/Users/dev/Code",), ["park"], "/Users/dev/Code"),
    ("unpark", ("/Users/dev/Code",), ["forget"], "/Users/dev/Code"),
    ("secure", ("loja",), ["secure", "loja"], None),
    ("unsecure", ("loja",), ["unsecure", "loja"], None),
    ("isolate", (LOJA, "8.4"), ["isolate", "php@8.4", "--site=loja"], None),
]


class SiteActionsTest(TempDirTestCase):
    def check(self, backend, table, binary):
        for method, args, argv, cwd in table:
            with self.subTest(backend=backend.name, method=method, args=args):
                fake = FakeRunner()
                backend.runner = fake
                result = getattr(backend, method)(*args)
                self.assertIsInstance(result, Result)
                self.assertEqual(len(fake.calls), 1)
                self.assertEqual(list(fake.calls[0].argv), [binary, *argv])
                self.assertEqual(fake.calls[0].cwd, cwd)

    def test_lerd(self):
        self.check(LerdBackend(LERD), LERD_TABLE, LERD)

    def test_valet(self):
        self.check(ValetBackend(VALET), VALET_TABLE, VALET)

    def test_valet_sem_node_isolado(self):
        with self.assertRaisesRegex(NotImplementedError, "Node"):
            ValetBackend(VALET).isolate_node(LOJA, "22")

    def test_codigo_diferente_de_zero_nao_levanta(self):
        fake = FakeRunner(default=Result(1, "", "versão recusada pelo framework"))
        result = LerdBackend(LERD, runner=fake).isolate(LOJA, "7.4")
        self.assertFalse(result.ok)
        self.assertIn("recusada", result.output)

    def test_valores_que_viram_opcao_sao_recusados(self):
        backend = LerdBackend(LERD, runner=FakeRunner())
        for method, args in (("secure", ("--help",)), ("isolate", (LOJA, "-8")), ("isolate_node", (LOJA, "--x")),
                             ("link", (LOJA, "-loja"))):
            with self.subTest(method=method):
                with self.assertRaises(ValueError):
                    getattr(backend, method)(*args)
        self.assertEqual(backend.runner.calls, [])

    def test_sem_backend_responde_sem_executar(self):
        fake = FakeRunner()
        backend = NullBackend(None, runner=fake)
        for method, args in (("link", (LOJA, "loja")), ("secure", ("loja",)), ("isolate", (LOJA, "8.4"))):
            with self.subTest(method=method):
                result = getattr(backend, method)(*args)
                self.assertFalse(result.ok)
                self.assertIn("Lerd ou Valet", result.output)
        self.assertEqual(fake.calls, [])
        self.assertEqual(backend.php_versions(), [])


class ShareTest(TempDirTestCase):
    def test_share_argv(self):
        lerd = LerdBackend(LERD)
        self.assertEqual(lerd.share_argv("loja"), [LERD, "share", "loja"])
        self.assertEqual(lerd.share_argv("loja", "cloudflare"), [LERD, "share", "loja", "--cloudflare"])
        self.assertEqual(lerd.share_argv("loja", "localhost-run"), [LERD, "share", "loja", "--localhost-run"])
        with self.assertRaises(ValueError):
            lerd.share_argv("loja", "outro")
        self.assertEqual(ValetBackend(VALET).share_argv("loja"), [VALET, "share"])


class PhpVersionsTest(TempDirTestCase):
    def test_versoes_da_api_do_lerd(self):
        status = json.loads((FIXTURES / "lerd-api-status.json").read_text(encoding="utf-8"))
        backend = LerdBackend(LERD)
        with mock.patch.object(backend, "api_get", return_value=status):
            versions = backend.php_versions()
        expected = sorted({str(f["version"]) for f in status.get("php_fpms", [])}, key=lambda v: [int(x) for x in v.split(".")])
        self.assertEqual([v["version"] for v in versions], expected)
        self.assertTrue(all("running" in v for v in versions))

    def test_api_fora_do_ar(self):
        backend = LerdBackend(LERD)
        with mock.patch.object(backend, "api_get", side_effect=OSError("recusada")):
            self.assertEqual(backend.php_versions(), [])
        self.assertEqual(ValetBackend(VALET).php_versions(), [])
