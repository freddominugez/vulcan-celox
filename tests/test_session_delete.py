import os
from pathlib import Path

from tests.helpers import WINDOWS
from tests.server_helpers import ServerTestCase
from vulcan_celox.core.session_memory import doc_path


class SessionDeleteTest(ServerTestCase):
    def env(self):
        env = super().env()
        env["SHELL"] = "/bin/sh"
        env["PATH"] = os.environ.get("PATH", "")
        return env

    def setUp(self):
        super().setUp()
        (self.tmp / "loja").mkdir()
        self.app.store.save("sites", {"loja": str(self.tmp / "loja")})

    def closed_session(self, title="migrations"):
        info = self.request("POST", "/api/terminals", body={"site": "loja", "title": title})[1]
        self.request("POST", "/api/tasks", body={"terminal": info["id"], "title": "tarefa da sessão"})
        self.request("POST", "/api/notes", body={"terminal": info["id"], "text": "nota da sessão"})
        self.request("DELETE", f"/api/terminals/{info['id']}")
        return info["id"], self.app.hub.sessions.get(info["id"]).memory_file

    def test_aberta_nao_apaga(self):
        info = self.request("POST", "/api/terminals", body={"site": "loja"})[1]
        self.assertEqual(self.request("DELETE", f"/api/sessions/{info['id']}")[0], 409)
        self.assertEqual(self.request("DELETE", "/api/sessions/abc123")[0], 404)

    def test_manter_itens_desvincula_e_move_arquivos(self):
        sid, memory = self.closed_session()
        doc = doc_path(memory)
        doc.write_text("# doc", encoding="utf-8")
        status, data, _ = self.request("DELETE", f"/api/sessions/{sid}?items=keep")
        self.assertEqual(status, 200)
        self.assertEqual((data["tasks"], data["notes"]), (1, 1))
        self.assertIsNone(self.app.hub.sessions.get(sid))
        self.assertFalse(Path(memory).exists())
        self.assertFalse(doc.exists())
        # tests use a fake runner: without the system Trash, files go to lixeira/ in the data folder
        trash = Path(self.app.data_dir) / "lixeira"
        if not WINDOWS:  # on Windows the system Trash is called directly, without the runner
            self.assertEqual(len(list(trash.iterdir())), 2)
        tasks = self.request("GET", "/api/tasks?site=loja")[1]["tasks"]
        self.assertEqual([(t["title"], t["terminal"]) for t in tasks], [("tarefa da sessão", "")])
        self.assertEqual(self.request("GET", "/api/notes?site=loja")[1]["notes"][0]["terminal"], "")
        self.assertNotIn(sid, self.request("GET", "/api/index/general")[1]["markdown"])
        self.assertEqual(self.request("GET", f"/api/sessions/{sid}")[0], 404)

    def test_apagar_itens(self):
        sid, _ = self.closed_session()
        self.assertEqual(self.request("DELETE", f"/api/sessions/{sid}?items=delete")[0], 200)
        self.assertEqual(self.request("GET", "/api/tasks?site=loja")[1]["tasks"], [])
        self.assertEqual(self.request("GET", "/api/notes?site=loja")[1]["notes"], [])
        self.assertEqual(self.request("DELETE", f"/api/sessions/{sid}?items=tudo")[0], 404)
        sid2, _ = self.closed_session("outra")
        self.assertEqual(self.request("DELETE", f"/api/sessions/{sid2}?items=tudo")[0], 400)
