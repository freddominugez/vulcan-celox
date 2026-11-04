"""PTY writes with a lock and a deadline. A large paste does not mix with keys from another thread and
a tab that does not read its input does not tie up the HTTP thread."""
import os
import threading
import time

from tests.helpers import TempDirTestCase, unix_only, WINDOWS
from vulcan_celox.core.pty_session import PtySession, terminal_env
from tests.test_pty import wait_for


class PtyEscritaTest(TempDirTestCase):
    def env(self):
        return terminal_env({"PATH": os.environ.get("PATH", ""), "HOME": str(self.tmp), "SHELL": "/bin/sh"})

    @unix_only("stty raw não existe no Windows")
    def test_duas_threads_nao_se_misturam(self):
        out = self.tmp / "saida"
        s = PtySession(["/bin/sh", "-c", f"stty raw -echo; exec cat > '{out}'"], str(self.tmp), self.env())
        self.addCleanup(s.close)
        time.sleep(0.3)  # stty before the write
        size = 64 * 1024
        threads = [threading.Thread(target=s.write, args=(ch * size,)) for ch in (b"A", b"B")]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        self.assertTrue(wait_for(lambda: out.is_file() and out.stat().st_size >= 2 * size, 10), out.stat().st_size if out.is_file() else 0)
        data = out.read_bytes()
        runs = sum(1 for i in range(1, len(data)) if data[i] != data[i - 1])
        self.assertEqual(runs, 1, f"{runs} trocas entre A e B")

    @unix_only("no Windows a escrita é bloqueante, sem prazo de desistência")
    def test_aba_que_nao_le_nao_prende_a_escrita(self):
        s = PtySession(["/bin/sh", "-c", "stty raw -echo; exec sleep 30"], str(self.tmp), self.env())
        self.addCleanup(s.close)
        time.sleep(0.3)
        done = []
        t = threading.Thread(target=lambda: done.append(s.write(b"x" * (1024 * 1024), timeout=0.5)), daemon=True)
        start = time.monotonic()
        t.start()
        t.join(5)
        self.assertFalse(t.is_alive(), "write ficou presa")
        self.assertLess(time.monotonic() - start, 4)
        self.assertEqual(done, [False])  # did not write everything: the caller finds out

    def test_escrita_normal_devolve_verdadeiro(self):
        s = PtySession(["cmd.exe"] if WINDOWS else ["/bin/sh"], str(self.tmp), self.env())
        self.addCleanup(s.close)
        self.assertTrue(s.write(b"set /a 1+1000\r" if WINDOWS else b"echo ok-$((1+1))\n"))
        self.assertTrue(wait_for(lambda: (b"1001" if WINDOWS else b"ok-2") in s.history()), s.history())
