from pathlib import Path

from tests.helpers import GOLDEN, TempDirTestCase
from tests.server_helpers import ServerTestCase
from vulcan_celox.core.models import Note, Tag, Task
from vulcan_celox.core.session_memory import memory_path, render_general_index
from vulcan_celox.core.sessions import SessionRecord


def records(data_dir):
    a = SessionRecord(id="000000000001", title="migrations", site="loja", cwd="/Users/dev/Code/loja",
                      tags=["t-banco"], commands=[{"ts": "2026-09-13T20:31:05Z", "cmd": "a"}, {"ts": "2026-09-13T20:32:05Z", "cmd": "b"}],
                      created_at="2026-09-13T20:30:00Z", closed_at="2026-09-13T21:35:30Z", exit_code=0)
    b = SessionRecord(id="000000000002", title="deploy", site="loja", cwd="/Users/dev/Code/loja",
                      commands=[{"ts": "2026-09-13T21:41:00Z", "cmd": "c"}], created_at="2026-09-13T21:40:00Z")
    c = SessionRecord(id="000000000003", title="anotações", site=None, cwd="/Users/dev",
                      created_at="2026-09-12T09:00:00Z", closed_at="2026-09-12T09:10:00Z")
    for record in (a, c):
        path = memory_path(data_dir, record)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# memória\n", encoding="utf-8")
        record.memory_file = str(path)
    return [a, b, c]


class GeneralIndexTest(TempDirTestCase):
    def test_golden_e_links(self):
        recs = records(self.tmp)
        tags = {"t-banco": Tag(id="t-banco", name="banco")}
        tasks = [Task(title="x", status="done", terminal="000000000001"), Task(title="y", terminal="000000000001"),
                 Task(title="z", terminal="000000000002"), Task(title="solta")]
        notes = [Note(text="n1", terminal="000000000001"), Note(text="n2", terminal="000000000003"), Note(text="solta")]
        Path(recs[0].memory_file[:-3] + ".doc.md").write_text("# doc\n", encoding="utf-8")
        (self.tmp / "DOCUMENTACAO.md").write_text("# geral\n", encoding="utf-8")
        text = render_general_index(recs, tasks, notes, tags, self.tmp)
        self.assertEqual(text, (GOLDEN / "INDICE-exemplo.md").read_text(encoding="utf-8"))
        import re
        for link in re.findall(r"\]\(((?:sessoes/|DOCUMENTACAO)[^)]+)\)", text):
            self.assertTrue((self.tmp / link).is_file(), link)

    def test_sem_sessoes(self):
        text = render_general_index([], [], [], {}, self.tmp)
        self.assertIn("_Nenhuma sessão de terminal ainda._", text)
        self.assertIn("Sessões: 0 (0 abertas, 0 encerradas)", text)


class GeneralIndexApiTest(ServerTestCase):
    def test_api_e_open_file(self):
        (self.tmp / "loja").mkdir()
        self.app.store.save("sites", {"loja": str(self.tmp / "loja")})
        info = self.request("POST", "/api/terminals", body={"site": "loja", "title": "indice"})[1]
        self.request("DELETE", f"/api/terminals/{info['id']}")
        data = self.request("GET", "/api/index/general")[1]
        self.assertTrue(data["path"].endswith("INDICE.md"))
        self.assertIn("## loja", data["markdown"])
        self.assertIn("indice", data["markdown"])
        self.assertTrue(Path(data["path"]).is_file())

        self.assertEqual(self.request("POST", "/api/open", body={"kind": "file", "target": "/etc/hosts"})[0], 400)
        self.assertEqual(self.request("POST", "/api/open", body={"kind": "file", "target": data["path"]})[0], 200)
        from vulcan_celox.core.oscompat import open_argv
        self.assertEqual(list(self.fake.calls[-1].argv), open_argv("file", str(Path(data["path"]).resolve()), self.app.env))
