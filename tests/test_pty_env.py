"""O shell da aba (e o agente iniciado nele) vê VULCAN_SESSION_ID e VULCAN_THEME."""

import os

from tests.helpers import TempDirTestCase
from tests.test_pty import wait_for
from vulcan_celox.core.pty_session import TerminalManager

PROBE = 'printf "id=[%s] tema=[%s]" "$VULCAN_SESSION_ID" "$VULCAN_THEME"'


class PtyEnvTest(TempDirTestCase):
    def manager(self, **extra):
        return TerminalManager({"PATH": os.environ.get("PATH", ""), "HOME": str(self.tmp), "SHELL": "/bin/sh", **extra})

    def test_processo_filho_ve_o_id_da_aba_e_o_tema(self):
        manager = self.manager()
        s = manager.create(str(self.tmp), command=PROBE, theme="oceano")
        expected = f"id=[{s.id}] tema=[oceano]".encode()
        self.assertTrue(wait_for(lambda: expected in s.history()), s.history())
        manager.close_all()

    def test_sem_tema_e_sem_heranca_de_outra_aba(self):
        # app aberto de dentro de um terminal do próprio Vulcan: o ambiente herdado não pode vazar para a aba nova
        manager = self.manager(VULCAN_SESSION_ID="aba-antiga", VULCAN_THEME="homebrew")
        s = manager.create(str(self.tmp), command=PROBE)
        expected = f"id=[{s.id}] tema=[]".encode()
        self.assertTrue(wait_for(lambda: expected in s.history()), s.history())
        self.assertNotIn(b"aba-antiga", s.history())
        manager.close_all()
