import os
import time

from tests.server_helpers import ServerTestCase


def wait_for(fn, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(0.05)
    return fn()


class SessionApiTest(ServerTestCase):
    def env(self):
        env = super().env()
        env["SHELL"] = "/bin/sh"
        env["PATH"] = os.environ.get("PATH", "")
        return env

    def setUp(self):
        super().setUp()
        self.loja = self.tmp / "loja"
        self.loja.mkdir()
        self.app.store.save("sites", {"loja": str(self.loja)})

    def open_terminal(self, **body):
        status, info, _ = self.request("POST", "/api/terminals", body={"site": "loja", **body})
        self.assertEqual(status, 201)
        return info

    def test_criar_terminal_registra_sessao(self):
        info = self.open_terminal()
        data = self.request("GET", "/api/sessions?site=loja")[1]
        self.assertEqual([s["id"] for s in data["open"]], [info["id"]])
        self.assertEqual(data["open"][0]["site"], "loja")
        self.assertTrue(data["open"][0]["live"])

    def test_itens_vinculados_herdam_site_e_filtram(self):
        a = self.open_terminal()
        b = self.open_terminal()
        t = self.request("POST", "/api/tasks", body={"terminal": a["id"], "title": "da sessão A"})[1]
        self.assertEqual((t["site"], t["terminal"], t["terminal_title"]), ("loja", a["id"], "loja"))
        self.request("POST", "/api/tasks", body={"terminal": b["id"], "title": "da sessão B"})
        self.request("POST", "/api/tasks", body={"site": "loja", "title": "do site sem sessão"})
        n = self.request("POST", "/api/notes", body={"terminal": a["id"], "text": "nota A"})[1]
        self.assertEqual(n["site"], "loja")

        so_a = self.request("GET", f"/api/tasks?site=loja&terminal={a['id']}")[1]["tasks"]
        self.assertEqual([x["title"] for x in so_a], ["da sessão A"])
        self.assertEqual(len(self.request("GET", "/api/tasks?site=loja")[1]["tasks"]), 3)
        self.assertEqual([x["text"] for x in self.request("GET", f"/api/notes?site=loja&terminal={a['id']}")[1]["notes"]],
                         ["nota A"])
        self.assertEqual(self.request("POST", "/api/tasks", body={"terminal": "abc999", "title": "x"})[0], 404)

        summary = next(s for s in self.request("GET", "/api/sessions?site=loja")[1]["open"] if s["id"] == a["id"])
        self.assertEqual((summary["tasks"]["total"], summary["notes"]), (1, 1))

    def test_tags_e_titulo_da_sessao(self):
        a = self.open_terminal()
        data = self.request("PATCH", f"/api/sessions/{a['id']}", body={"title": "migrations", "tags": ["banco", "deploy"]})[1]
        self.assertEqual(data["title"], "migrations")
        self.assertEqual([t["name"] for t in data["tags"]], ["banco", "deploy"])
        self.assertEqual(self.request("GET", "/api/terminals")[1]["terminals"][0]["title"], "migrations")
        tag_id = data["tags"][0]["id"]
        self.request("DELETE", f"/api/tags/{tag_id}")
        self.assertEqual([t["name"] for t in self.request("GET", f"/api/sessions/{a['id']}")[1]["tags"]], ["deploy"])
        self.assertEqual(self.request("GET", "/api/sessions/abc999")[0], 404)

    def test_fechar_e_sair_encerram_sessao(self):
        a = self.open_terminal()
        self.request("DELETE", f"/api/terminals/{a['id']}")
        split = self.request("GET", "/api/sessions?site=loja")[1]
        self.assertEqual([s["id"] for s in split["closed"]], [a["id"]])
        self.assertIsNotNone(split["closed"][0]["closed_at"])

        b = self.open_terminal(command="exit 3")
        wait_for(lambda: any(s["id"] == b["id"] for s in self.request("GET", "/api/sessions?site=loja")[1]["closed"]),
                 timeout=10.0)  # a Linux container under load takes longer to notice the output
        closed = {s["id"]: s for s in self.request("GET", "/api/sessions?site=loja")[1]["closed"]}
        self.assertIn(b["id"], closed)

    def test_processo_que_termina_antes_do_registro_encerra_a_sessao(self):
        session = self.app.terminals.create(str(self.loja), command="exit 3", site="loja")
        session._reader.join(10.0)  # the reader already delivered the end, to nobody
        self.assertFalse(session._reader.is_alive())
        self.app.hub.on_created(session)
        record = self.app.hub.sessions.get(session.id)
        self.assertFalse(record.is_open)
        self.assertEqual(record.exit_code, 3)

    def test_ocupado_e_memoria_ao_fechar(self):
        a = self.open_terminal()
        status, busy, _ = self.request("GET", f"/api/terminals/{a['id']}/busy")
        self.assertEqual(status, 200)
        self.assertIn("busy", busy)
        self.assertEqual(self.request("GET", "/api/terminals/abc999/busy")[0], 404)
        closed = self.request("DELETE", f"/api/terminals/{a['id']}")[1]
        self.assertTrue(closed["ok"])
        self.assertTrue(closed["memory_file"].endswith(".md"))
        self.assertTrue(os.path.isfile(closed["memory_file"]))
        index = self.request("GET", "/api/index/general")[1]
        self.assertIn(a["id"], index["markdown"])

    def test_dados_antigos_sem_terminal(self):
        self.app.store.save("tasks", [{"id": "a" * 32, "site": "loja", "title": "antiga"}])
        self.app.notebook.load()
        tasks = self.request("GET", "/api/tasks?site=loja")[1]["tasks"]
        self.assertEqual((tasks[0]["title"], tasks[0]["terminal"]), ("antiga", ""))
