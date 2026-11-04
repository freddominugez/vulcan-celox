"""The tab shell (and the agent started in it) sees VULCAN_SESSION_ID and VULCAN_THEME."""

import os

from tests.helpers import WINDOWS, TempDirTestCase
from tests.test_pty import wait_for
from vulcan_celox.core.pty_session import TerminalManager

PROBE = ('"id=[$env:VULCAN_SESSION_ID] tema=[$env:VULCAN_THEME]"' if WINDOWS
         else 'printf "id=[%s] tema=[%s]" "$VULCAN_SESSION_ID" "$VULCAN_THEME"')


class PtyEnvTest(TempDirTestCase):
    def manager(self, **extra):
        return TerminalManager({"PATH": os.environ.get("PATH", ""), "HOME": str(self.tmp), "SHELL": "/bin/sh", **extra})

    def test_processo_filho_ve_o_id_da_aba_e_o_tema(self):
        manager = self.manager()
        self.addCleanup(manager.close_all)
        s = manager.create(str(self.tmp), command=PROBE, theme="oceano")
        expected = f"id=[{s.id}] tema=[oceano]".encode()
        self.assertTrue(wait_for(lambda: expected in s.history(), timeout=15), s.history())

    def test_sem_tema_e_sem_heranca_de_outra_aba(self):
        # app opened from inside a Vulcan terminal itself: the inherited environment must not leak into the new tab
        manager = self.manager(VULCAN_SESSION_ID="aba-antiga", VULCAN_THEME="homebrew")
        self.addCleanup(manager.close_all)
        s = manager.create(str(self.tmp), command=PROBE)
        expected = f"id=[{s.id}] tema=[]".encode()
        self.assertTrue(wait_for(lambda: expected in s.history(), timeout=15), s.history())
        self.assertNotIn(b"aba-antiga", s.history())
