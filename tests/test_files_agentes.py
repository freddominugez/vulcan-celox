"""Who wrote: a session's record gives the name; without a record it is a disk change."""

import json
import time
import unittest
from datetime import datetime, timezone
from urllib.parse import quote

from tests.test_agents_api import AgentsServerCase

SID = "99999999-5555-4666-8777-888888888888"


def stamp(ago=0.0):
    return datetime.fromtimestamp(time.time() - ago, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class AtribuicaoTest(AgentsServerCase):
    def setUp(self):
        super().setUp()
        self.project = (self.tmp / "projeto").resolve()
        self.project.mkdir()
        self.root = str(self.project)
        self.jsonl = self.tmp / "claude" / "projects" / "-tmp-projeto" / f"{SID}.jsonl"
        self.jsonl.parent.mkdir(parents=True, exist_ok=True)
        self.lines = [{"type": "user", "timestamp": stamp(), "cwd": self.root, "message": {"role": "user", "content": "oi"}}]
        self.save()
        self.request("POST", "/api/files/roots", body={"path": self.root})
        self.cursor = self.changes()["cursor"]

    def save(self):
        self.jsonl.write_text("".join(json.dumps(x) + "\n" for x in self.lines), encoding="utf-8")
        self.app.agents.refresh()

    def record(self, name, ago=0.0, rel=False):
        tool = f"t{len(self.lines)}"
        path = name if rel else str(self.project / name)
        self.lines.append({"type": "assistant", "timestamp": stamp(ago), "cwd": self.root, "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": tool, "name": "Edit", "input": {"file_path": path, "old_string": "a", "new_string": "b"}}]}})
        self.save()

    def changes(self):
        return self.request("GET", f"/api/files/changes?root={quote(self.root)}" + (f"&since={self.cursor}" if getattr(self, "cursor", None) else ""))[1]

    def wait_event(self):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            data = self.changes()
            if data["events"]:
                self.cursor = data["cursor"]
                return data
            time.sleep(0.1)
        self.fail("nenhum evento")

    def test_escrita_externa_fica_sem_autor(self):
        (self.project / "externo.txt").write_text("x", encoding="utf-8")
        data = self.wait_event()
        self.assertIsNone(data["events"][0]["agent"])
        self.assertEqual(data["attributed"], [])

    def test_agente_registrado_antes_da_escrita(self):
        self.record("feito.py")
        self.app.files.attribution.cache.clear()
        (self.project / "feito.py").write_text("x", encoding="utf-8")
        data = self.wait_event()
        self.assertEqual(data["events"][0]["agent"], {"agent": "claude", "session": SID})

    def test_registro_que_chega_depois_atualiza_a_marca(self):
        (self.project / "tarde.py").write_text("x", encoding="utf-8")
        data = self.wait_event()
        self.assertIsNone(data["events"][0]["agent"])
        self.record("tarde.py")
        time.sleep(1.1)
        later = self.changes()
        self.assertEqual(later["events"], [])
        self.assertEqual(later["attributed"], [{"rel": "tarde.py", "agent": {"agent": "claude", "session": SID}}])

    def test_outro_caminho_nao_ganha_autor(self):
        self.record("outro.py")
        self.app.files.attribution.cache.clear()
        (self.project / "este.py").write_text("x", encoding="utf-8")
        self.assertIsNone(self.wait_event()["events"][0]["agent"])

    def test_registro_antigo_nao_conta(self):
        self.record("velho.py", ago=120)
        self.app.files.attribution.cache.clear()
        (self.project / "velho.py").write_text("x", encoding="utf-8")
        self.assertIsNone(self.wait_event()["events"][0]["agent"])

    def test_caminho_relativo_do_codex(self):
        self.record("sub.py", rel=True)
        self.app.files.attribution.cache.clear()
        (self.project / "sub.py").write_text("x", encoding="utf-8")
        self.assertEqual(self.wait_event()["events"][0]["agent"]["session"], SID)


if __name__ == "__main__":
    unittest.main()
