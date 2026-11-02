from tests.server_helpers import ServerTestCase


class NotebookApiTest(ServerTestCase):
    def test_ciclo_completo_e_indice(self):
        status, tag, _ = self.request("POST", "/api/tags", body={"name": "deploy"})
        self.assertEqual(status, 201)
        self.assertEqual(self.request("POST", "/api/tags", body={"name": "DEPLOY"})[0], 409)

        status, task, _ = self.request("POST", "/api/tasks", body={"site": "", "title": "Publicar versão",
                                                                    "priority": 1, "tags": ["deploy", "novo"]})
        self.assertEqual(status, 201)
        self.assertEqual([c["name"] for c in task["chips"]], ["deploy", "novo"])
        self.assertEqual(task["site"], "")

        self.assertEqual(self.request("POST", f"/api/tasks/{task['id']}/cycle", body={})[1]["status"], "doing")
        done = self.request("PATCH", f"/api/tasks/{task['id']}", body={"status": "done"})[1]
        self.assertIsNotNone(done["done_at"])

        prog = self.request("GET", "/api/progress")[1]
        self.assertEqual(prog["overall"]["pct"], 100)
        self.assertEqual(prog["tags"][tag["id"]]["label"], "1/1 · 100%")

        index = self.request("GET", "/api/index")[1]
        self.assertIn("Publicar versão", index["markdown"])
        self.assertIn("## Índice", index["markdown"])

        tags = self.request("GET", "/api/tags")[1]["tags"]
        self.assertEqual({t["name"]: t["usage"] for t in tags}, {"deploy": 1, "novo": 1})

    def test_validacoes(self):
        self.assertEqual(self.request("POST", "/api/tasks", body={"title": "x", "due": "2026-13-40"})[0], 400)
        self.assertEqual(self.request("POST", "/api/tasks", body={"title": "  "})[0], 400)
        self.assertEqual(self.request("POST", "/api/tasks", body={"title": "x", "priority": 9})[0], 400)
        self.assertEqual(self.request("PATCH", "/api/tasks/abc123", body={"title": "y"})[0], 404)
        self.assertEqual(self.request("DELETE", "/api/notes/abc123")[0], 404)
        self.assertEqual(self.request("POST", "/api/tasks", body={"title": "x", "tags": "nao-lista"})[0], 400)

    def test_filtros_de_tarefas(self):
        for title, status in (("a", "todo"), ("b", "done"), ("c", "doing")):
            t = self.request("POST", "/api/tasks", body={"site": "loja", "title": title})[1]
            self.request("PATCH", f"/api/tasks/{t['id']}", body={"status": status})
        self.request("POST", "/api/tasks", body={"title": "global"})
        abertas = self.request("GET", "/api/tasks?site=loja&status=todo,doing")[1]
        self.assertEqual(sorted(t["title"] for t in abertas["tasks"]), ["a", "c"])
        self.assertEqual(abertas["progress"]["label"], "1/3 · 33%")
        self.assertEqual(len(self.request("GET", "/api/tasks?site=*")[1]["tasks"]), 4)
        self.assertEqual([t["title"] for t in self.request("GET", "/api/tasks")[1]["tasks"]], ["global"])

    def test_notas_reordenar_e_busca(self):
        ids = [self.request("POST", "/api/notes", body={"site": "loja", "text": t})[1]["id"] for t in "abc"]
        self.request("POST", f"/api/notes/{ids[2]}/move", body={"index": 0})
        self.request("PATCH", f"/api/notes/{ids[1]}", body={"pinned": True, "color": "azul", "tags": ["infra"]})
        notes = self.request("GET", "/api/notes?site=loja")[1]["notes"]
        self.assertEqual([n["text"] for n in notes], ["b", "c", "a"])
        self.assertEqual((notes[0]["color"], notes[0]["chips"][0]["name"]), ("azul", "infra"))
        self.request("PATCH", f"/api/notes/{ids[0]}", body={"text": "Configurar NGINX"})
        hits = self.request("GET", "/api/search?q=nginx")[1]["hits"]
        self.assertEqual([(h["kind"], h["key"]) for h in hits], [("note", ids[0])])
        self.assertEqual(len(self.request("GET", "/api/notes?site=loja&q=nginx")[1]["notes"]), 1)

    def test_desfazer_exclusao(self):
        t = self.request("POST", "/api/tasks", body={"title": "apagar"})[1]
        self.assertEqual(self.request("DELETE", f"/api/tasks/{t['id']}")[0], 200)
        self.assertTrue(self.request("GET", "/api/tasks")[1]["can_undo"])
        self.assertEqual(self.request("POST", "/api/tasks/undo", body={})[1]["id"], t["id"])
        self.assertEqual(self.request("POST", "/api/tasks/undo", body={})[0], 410)

    def test_tags_renomear_cor_excluir(self):
        tag = self.request("POST", "/api/tags", body={"name": "bgu"})[1]
        self.request("POST", "/api/tasks", body={"title": "x", "tags": [tag["id"]]})
        updated = self.request("PATCH", f"/api/tags/{tag['id']}", body={"name": "bug", "color": "#3fa7f5"})[1]
        self.assertEqual((updated["name"], updated["color"]), ("bug", "#3fa7f5"))
        self.assertEqual(self.request("DELETE", f"/api/tags/{tag['id']}")[1]["affected"], 1)
        self.assertEqual(self.request("GET", "/api/tasks")[1]["tasks"][0]["chips"], [])

    def test_indice_do_projeto(self):
        projeto = self.tmp / "loja"
        projeto.mkdir()
        self.app.store.save("sites", {"loja": str(projeto)})
        self.request("POST", "/api/tasks", body={"site": "loja", "title": "Tarefa do projeto"})
        status, data, _ = self.request("POST", "/api/index/project", body={"site": "loja", "enabled": True})
        self.assertEqual(status, 200)
        self.assertIn("Tarefa do projeto", (projeto / "TAREFAS.md").read_text(encoding="utf-8"))
        self.assertTrue(self.request("GET", "/api/index/project?site=loja")[1]["enabled"])
        self.assertEqual(self.request("POST", "/api/index/project", body={"site": "fantasma", "enabled": True})[0],
                         404)
