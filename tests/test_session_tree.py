import os

from tests.server_helpers import ServerTestCase
from vulcan_celox.core.session_memory import doc_path


class SessionTreeTest(ServerTestCase):
    def env(self):
        env = super().env()
        env["SHELL"] = "/bin/sh"
        env["PATH"] = os.environ.get("PATH", "")
        return env

    def setUp(self):
        super().setUp()
        (self.tmp / "loja").mkdir()
        self.app.store.save("sites", {"loja": str(self.tmp / "loja")})

    def open_terminal(self, site="loja"):
        return self.request("POST", "/api/terminals", body={"site": site})[1]

    def test_arvore_com_itens_limite_e_documentacao(self):
        a = self.open_terminal()
        b = self.open_terminal()
        c = self.open_terminal(site=None)
        self.request("POST", "/api/tasks", body={"terminal": a["id"], "title": "feita"})
        doing = self.request("POST", "/api/tasks", body={"terminal": a["id"], "title": "andando"})[1]
        self.request("PATCH", f"/api/tasks/{doing['id']}", body={"status": "doing"})
        self.request("POST", "/api/notes", body={"terminal": a["id"], "text": "lembrar do cache\nsegunda linha"})
        self.request("PATCH", f"/api/sessions/{a['id']}", body={"tags": ["deploy"]})
        self.request("DELETE", f"/api/terminals/{b['id']}")
        self.request("DELETE", f"/api/terminals/{c['id']}")

        tree = self.request("GET", "/api/sessions/tree")[1]
        self.assertEqual([s["id"] for s in tree["open"]], [a["id"]])
        self.assertEqual({s["id"] for s in tree["closed"]}, {b["id"], c["id"]})
        self.assertEqual(tree["closed_total"], 2)
        node = tree["open"][0]
        self.assertEqual([t["title"] for t in node["task_list"]], ["andando", "feita"])
        self.assertEqual(node["note_list"][0]["title"], "lembrar do cache")
        self.assertEqual([t["name"] for t in node["tags"]], ["deploy"])
        self.assertFalse(node["has_doc"])
        global_node = next(s for s in tree["closed"] if s["id"] == c["id"])
        self.assertEqual(global_node["site"], "")

        closed_b = next(s for s in tree["closed"] if s["id"] == b["id"])
        doc = doc_path(closed_b["memory_file"])
        self.assertTrue(str(doc).endswith(f"{b['id']}.doc.md"))
        doc.write_text("# doc", encoding="utf-8")
        limited = self.request("GET", "/api/sessions/tree?closed=1")[1]
        self.assertEqual((len(limited["closed"]), limited["closed_total"]), (1, 2))
        again = {s["id"]: s for s in self.request("GET", "/api/sessions/tree")[1]["closed"]}
        self.assertTrue(again[b["id"]]["has_doc"])
        self.assertEqual(self.request("GET", "/api/sessions/tree?closed=x")[0], 400)
        more = self.request("GET", "/api/sessions/tree?closed=60")[1]  # "Carregar mais" aumenta o limite
        self.assertEqual((len(more["closed"]), more["closed_total"]), (2, 2))
