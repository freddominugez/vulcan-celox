import os
import threading
import time
import unittest

from tests.helpers import TempDirTestCase
from vulcan_terminal.core.pty_session import HISTORY_LIMIT, PtySession, TerminalManager, terminal_env


def wait_for(fn, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(0.05)
    return fn()


class PtyTest(TempDirTestCase):
    def env(self):
        return terminal_env({"PATH": os.environ.get("PATH", ""), "HOME": str(self.tmp), "SHELL": "/bin/sh"})

    def test_saida_de_comando(self):
        s = PtySession(["/bin/sh", "-c", "printf ola"], str(self.tmp), self.env())
        self.assertTrue(wait_for(lambda: b"ola" in s.history()))
        wait_for(lambda: s.exit_code is not None)
        self.assertEqual(s.exit_code, 0)
        s.close()

    def test_resize_reflete_no_stty(self):
        s = PtySession(["/bin/sh"], str(self.tmp), self.env(), rows=24, cols=80)
        s.resize(30, 100)
        s.write(b"stty size\n")
        self.assertTrue(wait_for(lambda: b"30 100" in s.history()), s.history())
        s.close()

    def test_entrada_interativa_e_cwd(self):
        s = PtySession(["/bin/sh"], str(self.tmp), self.env())
        s.write(b"echo resultado=$((2+3)); pwd\n")
        self.assertTrue(wait_for(lambda: b"resultado=5" in s.history()), s.history())
        self.assertTrue(wait_for(lambda: os.path.realpath(str(self.tmp)).encode() in s.history()))
        s.close()

    def test_historico_e_ouvintes(self):
        s = PtySession(["/bin/sh"], str(self.tmp), self.env())
        s.write(b"echo primeiro\n")
        self.assertTrue(wait_for(lambda: b"primeiro" in s.history()))
        received = []
        history = s.subscribe(received.append)
        self.assertIn(b"primeiro", history)
        s.write(b"echo segundo\n")
        self.assertTrue(wait_for(lambda: b"segundo" in b"".join(c for c in received if c)))
        s.close()

    def test_close_mata_rapido(self):
        s = PtySession(["/bin/sh", "-c", "trap '' HUP; sleep 60"], str(self.tmp), self.env())
        time.sleep(0.2)
        start = time.monotonic()
        s.close()
        self.assertLess(time.monotonic() - start, 3.0)
        self.assertFalse(s.alive)
        with self.assertRaises(ProcessLookupError):
            os.kill(s.pid, 0)

    def test_fim_do_processo_avisa_ouvinte(self):
        s = PtySession(["/bin/sh", "-c", "sleep 0.3"], str(self.tmp), self.env())
        ended = threading.Event()
        s.subscribe(lambda chunk: chunk is None and ended.set())
        self.assertTrue(ended.wait(5))
        s.close()

    def test_limite_do_historico(self):
        s = PtySession(["/bin/sh", "-c", f"head -c {HISTORY_LIMIT + 50000} /dev/zero | tr '\\\\0' x"],
                       str(self.tmp), self.env())
        wait_for(lambda: s.exit_code is not None, timeout=10)
        self.assertLessEqual(len(s.history()), HISTORY_LIMIT)
        s.close()


class ManagerTest(TempDirTestCase):
    def test_env_e_argv(self):
        env = terminal_env({"PATH": "/usr/bin", "HOME": "/Users/dev", "VULCAN_TOKEN": "segredo"})
        self.assertTrue(env["PATH"].startswith("/Users/dev/.local/share/lerd/bin:/Users/dev/.local/bin"))
        self.assertEqual(env["TERM"], "xterm-256color")
        self.assertNotIn("VULCAN_TOKEN", env)
        mgr = TerminalManager({"SHELL": "/bin/sh"})  # existe em macOS e Linux
        self.assertEqual(mgr.argv_for(None), ["/bin/sh", "-l"])
        self.assertEqual(mgr.argv_for("php artisan tinker")[-1], "php artisan tinker; exec /bin/sh -l")

    def test_criar_listar_fechar(self):
        mgr = TerminalManager({"PATH": os.environ.get("PATH", ""), "HOME": str(self.tmp), "SHELL": "/bin/sh"})
        a = mgr.create(str(self.tmp), title="a")
        b = mgr.create(str(self.tmp), command="echo oi", title="b")
        self.assertEqual([s.id for s in mgr.list()], [a.id, b.id])
        c = mgr.create(str(self.tmp), title="a")
        self.assertEqual(c.title, "a 2")
        self.assertTrue(wait_for(lambda: b"oi" in b.history()))
        self.assertTrue(mgr.close(a.id))
        self.assertFalse(mgr.close(a.id))
        mgr.close_all()
        self.assertEqual(mgr.list(), [])


if __name__ == "__main__":
    unittest.main()
