"""End-to-end acceptance of the tab, session and prompt path, with a real PTY and shell.

Only the agent is fake: an executable named `claude` that writes the session the way Claude Code does and records what
arrives through the terminal. It never runs the real Claude Code and never touches ~/.claude. The server, the index, the pairing by folder
and time, the foreground process reading and the paste are the production ones.
"""

import datetime
import os
import sys
import time

from tests.helpers import unix_only
from tests.server_helpers import ServerTestCase
from tests.test_pty import wait_for
from vulcan_celox.core import procinfo, prompts

SID = "aaaaaaaa-1111-4222-8333-444444444444"

FAKE_AGENT = """#!{python}
import json, os, select, sys, termios, tty
base, sid, cwd, at = {base!r}, {sid!r}, {cwd!r}, {at!r}
folder = os.path.join(base, "claude", "projects", "-projeto")
os.makedirs(folder, exist_ok=True)
line = {{"type": "user", "sessionId": sid, "cwd": cwd, "timestamp": at, "uuid": "u1", "parentUuid": None,
         "message": {{"role": "user", "content": "crie o cupom"}}}}
with open(os.path.join(folder, sid + ".jsonl"), "w") as fh:
    fh.write(json.dumps(line) + "\\n")
tty.setraw(0)  # como a interface do agente: recebe os bytes crus, sem esperar Enter
with open(os.path.join(base, "recebido"), "ab", buffering=0) as out:
    while not os.path.exists(os.path.join(base, "parar")):
        if select.select([0], [], [], 0.05)[0]:
            out.write(os.read(0, 65536))
"""


@unix_only("agente falso com termios, e o Windows não tem checagem de primeiro plano")
class AceiteTest(ServerTestCase):
    def env(self):
        env = super().env()
        (self.tmp / "projeto").mkdir()
        (self.tmp / "codex").mkdir()
        env.update({"CLAUDE_CONFIG_DIR": str(self.tmp / "claude"), "CODEX_HOME": str(self.tmp / "codex"),
                    "SHELL": "/bin/sh", "PATH": os.environ.get("PATH", ""), "VULCAN_AGENTS": "0"})
        return env

    def tearDown(self):
        (self.tmp / "parar").touch()  # the fake agent exits on its own
        self.app.terminals.close_all()
        super().tearDown()

    def send(self):
        status, data, _ = self.request("POST", "/api/prompts/send", body={
            "prompt": "seguranca", "session": SID, "values": {"branch": "main", "projectName": "projeto"}})
        return status, data

    def received(self):
        path = self.tmp / "recebido"
        return path.read_bytes() if path.exists() else b""

    def card(self):
        self.app.agents.refresh()
        status, data, _ = self.request("GET", "/api/agents/sessions")
        self.assertEqual(status, 200, data)
        return next((s for s in data["sessions"] if s["id"] == SID), None)

    def test_aba_sessao_e_prompt(self):
        cwd = str(self.tmp / "projeto")
        status, tab, _ = self.request("POST", "/api/terminals", body={"cwd": cwd, "rows": 24, "cols": 80})
        self.assertEqual(status, 201, tab)
        terminal = self.app.terminals.get(tab["id"])
        agent = self.tmp / "bin" / "claude"
        agent.parent.mkdir()
        at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        agent.write_text(FAKE_AGENT.format(python=sys.executable, base=str(self.tmp), sid=SID, cwd=cwd, at=at))
        agent.chmod(0o755)

        # no agent in the tab: no session exists yet
        self.assertIsNone(self.card())
        self.assertTrue(terminal.write(f"'{agent}'\n".encode()))

        # the session shows up paired with the tab, without a hook: folder and time
        session = wait_for(lambda: (self.card() or {}).get("pairing_id") and self.card(), timeout=15)
        self.assertTrue(session, "a sessão não apareceu pareada")
        self.assertEqual(session["pairing_id"], tab["id"])

        # the foreground agent receives the paste, without Enter. Only one: the repeated send only happens if refused
        results = []
        self.assertTrue(wait_for(lambda: results.append(self.send()) or results[-1][0] == 200, timeout=10), results)
        self.assertTrue(wait_for(lambda: prompts.PASTE_END in self.received(), timeout=10), self.received())
        data = self.received()
        self.assertEqual((data.count(prompts.PASTE_START), data.count(prompts.PASTE_END)), (1, 1))
        self.assertTrue(data.startswith(prompts.PASTE_START) and data.endswith(prompts.PASTE_END))
        self.assertIn(f"sessão {SID}".encode(), data)
        self.assertNotIn(b"\r", data)
        self.assertNotIn(b"\n", data)

        # the agent closes, the tab goes back to the shell: the pairing expires and nothing goes to the shell
        (self.tmp / "parar").touch()
        self.assertTrue(wait_for(lambda: not procinfo.agent_running(terminal.foreground() or [("claude", "claude")], "claude"),
                                 timeout=15), terminal.foreground())
        status, refused = self.send()
        self.assertEqual((status, refused["needs_terminal"], refused["session"]), (409, True, SID))
        self.assertEqual(self.received(), data)
        self.assertTrue(terminal.alive)
        time.sleep(0.2)
        self.assertNotIn(SID.encode(), terminal.history())  # the shell did not receive the text
