"""Detector of a possible test loop."""

import json
import unittest

from tests.helpers import TempDirTestCase
from vulcan_celox.core.agents.loops import LoopTracker
from vulcan_celox.core.agents.reading import read_session


class LoopTrackerTest(unittest.TestCase):
    def test_tres_execucoes_sem_commit_disparam(self):
        t = LoopTracker()
        t.feed("php artisan test --filter=Frete", "t1")
        t.feed("php artisan test --filter=Frete", "t2")
        self.assertIsNone(t.alert())
        t.feed("cd /x && php artisan test --filter=Frete | tail -5", "t3")
        self.assertEqual(t.alert(), {"command": "php artisan test --filter=Frete", "count": 3, "since": "t1", "last_at": "t3"})

    def test_so_o_commit_que_deu_certo_zera(self):
        # the text "git commit" does not reset on its own (the commit may have failed); the assembler calls reset()
        t = LoopTracker()
        for i in range(4):
            t.feed("pytest -x", f"t{i}")
        t.feed("git commit -m tentativa", "t5")
        self.assertEqual(t.alert()["count"], 4)
        t.reset()
        self.assertIsNone(t.alert())
        t.feed("pytest -x", "t6")
        self.assertIsNone(t.alert())

    def test_testes_diferentes_contam_separado_e_vence_o_maior(self):
        t = LoopTracker()
        for i, cmd in enumerate(["pytest a", "pytest b", "pytest a", "pytest b", "pytest a", "ls", "git status"]):
            t.feed(cmd, f"t{i}")
        self.assertEqual(t.alert()["command"], "pytest a")
        self.assertEqual(t.alert()["count"], 3)

    def test_estado_serializavel(self):
        t = LoopTracker()
        for i in range(2):
            t.feed("npm test", f"t{i}")
        t2 = LoopTracker(json.loads(json.dumps(t.state())))
        t2.feed("npm test", "t9")
        self.assertEqual(t2.alert()["count"], 3)


class LoopNaSessaoTest(TempDirTestCase):
    def test_seis_testes_sem_commit_na_sessao(self):
        lines = [{"type": "user", "timestamp": "2026-10-30T10:00:00Z", "cwd": "/Users/dev/loja",
                  "message": {"role": "user", "content": "corrija"}}]
        for i in range(6):
            lines.append({"type": "assistant", "timestamp": f"2026-10-30T10:0{i + 1}:00Z", "message": {
                "id": f"m{i}", "usage": {}, "content": [
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "/Users/dev/loja/a.php"}},
                    {"type": "tool_use", "name": "Bash", "input": {"command": "php artisan test --filter=Frete"}}]}})
        path = self.tmp / "s.jsonl"
        path.write_text("".join(json.dumps(o) + "\n" for o in lines), encoding="utf-8")
        s = read_session("claude", path).session
        self.assertEqual(s.loop_alert["count"], 6)
        self.assertEqual(s.loop_alert["since"], "2026-10-30T10:01:00Z")


if __name__ == "__main__":
    unittest.main()
