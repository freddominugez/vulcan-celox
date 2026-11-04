import tempfile
import threading
import time
import unittest
from pathlib import Path

from tests.helpers import WINDOWS, py_argv
from vulcan_celox.core.runner import FakeRunner, Result, Runner


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.runner = Runner()

    def test_echo(self):
        r = self.runner.run(py_argv("print('ola')"))
        self.assertEqual(r.code, 0)
        self.assertEqual(r.stdout.strip(), "ola")
        self.assertFalse(r.timed_out)

    def test_arquivo_que_nao_e_programa_retorna_126(self):
        with tempfile.TemporaryDirectory() as pasta:
            falso = Path(pasta) / "nao-e-programa"
            falso.write_bytes(b"isto nao executa\n")
            falso.chmod(0o755)
            self.assertEqual(self.runner.run([str(falso)]).code, 126)

    def test_inexistente_retorna_127(self):
        r = self.runner.run(["/nao/existe/comando-vulcan"])
        self.assertEqual(r.code, 127)

    def test_timeout(self):
        start = time.monotonic()
        r = self.runner.run(py_argv("import time; time.sleep(10)"), timeout=0.3)
        self.assertEqual(r.code, -1)
        self.assertTrue(r.timed_out)
        self.assertLess(time.monotonic() - start, 4)

    def test_run_shell_usa_shell_padrao(self):
        from vulcan_celox.core.runner import SHELL
        if WINDOWS:
            r = self.runner.run_shell("echo ('mar' + 'ca')")
            self.assertEqual((r.code, r.stdout.strip()), (0, "marca"), SHELL)
            return
        r = self.runner.run_shell("echo $0")
        self.assertEqual(r.code, 0)
        self.assertIn(SHELL.rsplit("/", 1)[-1], r.stdout)

    def test_stream_entrega_linhas_em_ordem(self):
        lines, codes = [], []
        done = threading.Event()
        h = self.runner.stream(py_argv("for i in (1, 2, 3): print(i)"),
                               on_line=lines.append,
                               on_exit=lambda c: (codes.append(c), done.set()))
        self.assertTrue(done.wait(5))
        self.assertTrue(h.wait(5))
        self.assertEqual(lines, ["1", "2", "3"])
        self.assertEqual(codes, [0])

    def test_cancel_encerra_rapido(self):
        done = threading.Event()
        h = self.runner.stream(py_argv("import time; time.sleep(30)"), on_exit=lambda _c: done.set())
        time.sleep(0.1)
        start = time.monotonic()
        h.cancel()
        self.assertTrue(done.wait(4))
        self.assertLess(time.monotonic() - start, 4)
        self.assertTrue(h.cancelled)
        self.assertFalse(h.running)

    def test_stream_inexistente(self):
        codes = []
        self.runner.stream(["/nao/existe"], on_exit=codes.append)
        self.assertEqual(codes, [127])


class FakeRunnerTest(unittest.TestCase):
    def test_registra_e_responde(self):
        fake = FakeRunner()
        fake.respond(["valet", "links"], Result(0, "saida"))
        self.assertEqual(fake.run(["valet", "links"], cwd="/x").stdout, "saida")
        self.assertEqual(fake.run(["outro"]).code, 0)
        self.assertEqual(fake.calls[0].argv, ("valet", "links"))
        self.assertEqual(fake.calls[0].cwd, "/x")

    def test_stream_fake(self):
        fake = FakeRunner()
        fake.respond(["x"], Result(2, "a\nb"))
        lines, codes = [], []
        h = fake.stream(["x"], on_line=lines.append, on_exit=codes.append)
        h.cancel()
        self.assertEqual((lines, codes, h.cancel_calls), (["a", "b"], [2], 1))
