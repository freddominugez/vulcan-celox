"""Processos do grupo em primeiro plano da aba, com PTY real e /proc falso."""
import os
import shutil

from tests.helpers import TempDirTestCase
from tests.test_pty import wait_for
from vulcan_celox.core import procinfo
from vulcan_celox.core.pty_session import PtySession, terminal_env
from vulcan_celox.core.runner import FakeRunner, Result


class AgentRunningTest(TempDirTestCase):
    def test_nomes(self):
        self.assertTrue(procinfo.agent_running([("claude", "claude --resume x")], "claude"))
        self.assertTrue(procinfo.agent_running([("node", "node /opt/homebrew/bin/codex")], "codex"))
        self.assertTrue(procinfo.agent_running([("2.1.3", "/Users/dev/.local/share/claude/versions/2.1.3")], "claude"))
        self.assertFalse(procinfo.agent_running([("-zsh", "-zsh")], "claude"))
        self.assertFalse(procinfo.agent_running([("codex", "/Users/dev/.codex/packages/standalone/current/bin/codex")], "claude"))
        self.assertFalse(procinfo.agent_running([], "codex"))
        self.assertFalse(procinfo.agent_running([("cat", "cat /Users/dev/notas/x claude")], "claude"))  # só os dois primeiros

    def test_ps_pelo_runner(self):
        runner = FakeRunner({("ps", "-A", "-o", "pgid=", "-o", "args="):
                             Result(0, "  10 -zsh\n  42 claude --resume abc\n  42 /bin/sleep 1\n 7 outro\n")})
        procs = procinfo.group_processes(42, runner=runner, proc_root=self.tmp / "sem-proc")
        self.assertEqual(procs, [("claude", "claude --resume abc"), ("sleep", "/bin/sleep 1")])
        runner = FakeRunner(default=Result(1, ""))
        self.assertIsNone(procinfo.group_processes(42, runner=runner, proc_root=self.tmp / "sem-proc"))
        self.assertIsNone(procinfo.group_processes(None))

    def test_proc_falso(self):
        root = self.tmp / "proc"
        (root / "self").mkdir(parents=True)
        for pid, comm, pgrp, cmd in ((10, "zsh", 10, b"-zsh\0"), (42, "my (agent)", 42, b"claude\0--resume\0x\0"),
                                     (43, "sleep", 42, b"sleep\x001\0")):
            (root / str(pid)).mkdir()
            (root / str(pid) / "stat").write_text(f"{pid} ({comm}) S 1 {pgrp} {pgrp} 0 -1\n")
            (root / str(pid) / "cmdline").write_bytes(cmd)
        procs = procinfo.group_processes(42, proc_root=root)
        self.assertEqual(sorted(procs), [("my (agent)", "claude --resume x"), ("sleep", "sleep 1")])


class ForegroundPtyTest(TempDirTestCase):
    def env(self):
        return terminal_env({"PATH": os.environ.get("PATH", ""), "HOME": str(self.tmp), "SHELL": "/bin/sh"})

    def test_processo_em_primeiro_plano_da_aba(self):
        # um "agente" falso: um executável chamado claude que só espera
        bindir = self.tmp / "bin"
        bindir.mkdir()
        fake = bindir / "claude"
        fake.write_text("#!/bin/sh\nsleep 30\n")  # sem exec: fica /bin/sh .../claude
        fake.chmod(0o755)
        s = PtySession(["/bin/sh", "-c", f"exec '{shutil.which('sleep')}' 30"], str(self.tmp), self.env())
        self.addCleanup(s.close)
        # o primeiro olhar pode pegar o sh antes do exec (Linux): espera o sleep aparecer
        has_sleep = lambda: any(os.path.basename(c) == "sleep" or "sleep" in a for c, a in (s.foreground() or []))
        self.assertTrue(wait_for(has_sleep), s.foreground())
        self.assertFalse(procinfo.agent_running(s.foreground(), "claude"))
        a = PtySession(["/bin/sh", "-c", f"'{fake}'; :"], str(self.tmp), self.env())
        self.addCleanup(a.close)
        self.assertTrue(wait_for(lambda: procinfo.agent_running(a.foreground() or [], "claude")), a.foreground())
        self.assertFalse(procinfo.agent_running(a.foreground(), "codex"))
