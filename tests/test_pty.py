import os
import threading
import time
import unittest

from tests.helpers import WINDOWS, TempDirTestCase, py_argv, unix_only
from vulcan_celox.core.pty_session import HISTORY_LIMIT, PtySession, TerminalManager, terminal_env


SHELL = ["cmd.exe"] if WINDOWS else ["/bin/sh"]


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
        s = PtySession(py_argv("import sys; sys.stdout.write('ola')"), str(self.tmp), self.env())
        self.assertTrue(wait_for(lambda: b"ola" in s.history()))
        wait_for(lambda: s.exit_code is not None)
        self.assertEqual(s.exit_code, 0)
        s.close()

    @unix_only("stty não existe no Windows (resize em tests/test_windows.py)")
    def test_resize_reflete_no_stty(self):
        s = PtySession(["/bin/sh"], str(self.tmp), self.env(), rows=24, cols=80)
        s.resize(30, 100)
        s.write(b"stty size\n")
        self.assertTrue(wait_for(lambda: b"30 100" in s.history()), s.history())
        s.close()

    def test_entrada_interativa_e_cwd(self):
        s = PtySession(SHELL, str(self.tmp), self.env(), cols=300)
        self.addCleanup(s.close)
        if WINDOWS:
            s.write(b"set /a 2000+3 & cd\r")
            self.assertTrue(wait_for(lambda: b"2003" in s.history()), s.history())
            self.assertTrue(wait_for(lambda: self.tmp.name.encode() in s.history()), s.history())
            return
        s.write(b"echo resultado=$((2+3)); pwd\n")
        self.assertTrue(wait_for(lambda: b"resultado=5" in s.history()), s.history())
        self.assertTrue(wait_for(lambda: os.path.realpath(str(self.tmp)).encode() in s.history()))

    def test_historico_e_ouvintes(self):
        s = PtySession(SHELL, str(self.tmp), self.env())
        self.addCleanup(s.close)
        s.write(b"echo primeiro\r")
        self.assertTrue(wait_for(lambda: b"primeiro" in s.history()))
        received = []
        history = s.subscribe(received.append)
        self.assertIn(b"primeiro", history)
        s.write(b"echo segundo\r")
        self.assertTrue(wait_for(lambda: b"segundo" in b"".join(c for c in received if c)))

    def test_close_mata_rapido(self):
        s = PtySession(py_argv("import time; time.sleep(60)") if WINDOWS else ["/bin/sh", "-c", "trap '' HUP; sleep 60"],
                       str(self.tmp), self.env())
        time.sleep(0.2)
        start = time.monotonic()
        s.close()
        self.assertLess(time.monotonic() - start, 3.0)
        self.assertFalse(s.alive)
        if not WINDOWS:  # there os.kill(pid, 0) ends the process; the end of the tree is in tests/test_windows.py
            with self.assertRaises(ProcessLookupError):
                os.kill(s.pid, 0)

    def test_fim_do_processo_avisa_ouvinte(self):
        s = PtySession(py_argv("import time; time.sleep(0.3)"), str(self.tmp), self.env())
        ended = threading.Event()
        s.subscribe(lambda chunk: chunk is None and ended.set())
        self.assertTrue(ended.wait(5))
        s.close()

    def test_limite_do_historico(self):
        s = PtySession(py_argv(f"import sys; sys.stdout.write('x' * {HISTORY_LIMIT + 50000})"), str(self.tmp), self.env())
        wait_for(lambda: s.exit_code is not None, timeout=10)
        self.assertLessEqual(len(s.history()), HISTORY_LIMIT)
        s.close()


class ManagerTest(TempDirTestCase):
    @unix_only("PATH e shell do Unix (Windows em tests/test_windows.py)")
    def test_env_e_argv(self):
        env = terminal_env({"PATH": "/usr/bin", "HOME": "/Users/dev", "VULCAN_TOKEN": "segredo"})
        self.assertTrue(env["PATH"].startswith("/Users/dev/.local/share/lerd/bin:/Users/dev/.local/bin"))
        self.assertEqual(env["TERM"], "xterm-256color")
        self.assertNotIn("VULCAN_TOKEN", env)
        mgr = TerminalManager({"SHELL": "/bin/sh"})  # exists on macOS and Linux
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
