from datetime import date

from tests.helpers import TempDirTestCase
from tests.server_helpers import ServerTestCase
from vulcan_terminal.core.models import Task
from vulcan_terminal.core.notebook import NO_ASSIGNEE, Notebook, task_summary
from vulcan_terminal.core.store import Store

HOJE = date(2026, 9, 14)


class TasksManagerCoreTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.nb = Notebook(Store(self.tmp))
        self.a = self.nb.add_task("loja", "atrasada", due="2026-09-10", assignee="  Ana   Souza ")
        self.b = self.nb.add_task("loja", "hoje", due="2026-09-14", assignee="bruno")
        self.c = self.nb.add_task("loja", "semana", due="2026-09-19")
        self.d = self.nb.add_task("loja", "longe", due="2026-10-30", assignee="Ana Souza")
        self.e = self.nb.add_task("loja", "feita atrasada", due="2026-09-01", assignee="Bruno")
        self.nb.update_task(self.e.id, status="done")

    def titles(self, **kw):
        return sorted(t.title for t in self.nb.filter_tasks("loja", today=HOJE, **kw))

    def test_responsavel_normalizado_e_filtros(self):
        self.assertEqual(self.a.assignee, "Ana Souza")
        self.assertEqual(self.titles(assignee="ana souza"), ["atrasada", "longe"])
        self.assertEqual(self.titles(assignee=NO_ASSIGNEE), ["semana"])
        self.assertEqual(self.titles(due="late"), ["atrasada"])  # concluída não conta como atrasada
        self.assertEqual(self.titles(due="today"), ["hoje"])
        self.assertEqual(self.titles(due="week"), ["hoje", "semana"])
        self.nb.update_task(self.c.id, assignee="Carla")
        self.assertEqual(self.nb.task(self.c.id).assignee, "Carla")
        self.nb.update_task(self.c.id, assignee="")
        self.assertIsNone(self.nb.task(self.c.id).assignee)

    def test_resumo_e_ordem(self):
        summary = task_summary(self.nb.filter_tasks("loja"), today=HOJE)
        self.assertEqual(summary, {"total": 5, "open": 4, "done": 1, "late": 1, "today": 1, "unassigned": 1})
        ordered = [t.assignee for t in self.nb.filter_tasks("loja", sort="assignee")]
        self.assertEqual(ordered[-1], None)
        self.assertEqual(ordered[0], "Ana Souza")

    def test_dados_antigos_e_limite(self):
        old = Task.from_dict({"id": "a" * 32, "title": "antiga"})
        self.assertIsNone(old.assignee)
        self.assertEqual(len(Task.from_dict({"id": "b" * 32, "title": "x", "assignee": "n" * 200}).assignee), 60)
        self.assertIsNone(Task.from_dict({"id": "c" * 32, "title": "x", "assignee": 42}).assignee)


class TasksManagerApiTest(ServerTestCase):
    def test_api(self):
        self.app.store.save("sites", {"loja": str(self.tmp)})
        t = self.request("POST", "/api/tasks", body={"site": "loja", "title": "deploy", "assignee": "Ana", "due": "2020-01-01"})[1]
        self.assertEqual(t["assignee"], "Ana")
        self.request("POST", "/api/tasks", body={"site": "loja", "title": "sem dono"})
        self.request("PATCH", f"/api/tasks/{t['id']}", body={"assignee": "Bruno"})
        data = self.request("GET", "/api/tasks?site=loja&assignee=bruno")[1]
        self.assertEqual([x["title"] for x in data["tasks"]], ["deploy"])
        self.assertEqual(data["summary"]["unassigned"], 1)
        self.assertEqual(data["summary"]["late"], 1)
        self.assertEqual([x["title"] for x in self.request("GET", "/api/tasks?site=loja&due=late")[1]["tasks"]], ["deploy"])
        self.assertEqual([x["title"] for x in self.request("GET", "/api/tasks?site=loja&assignee=__sem__")[1]["tasks"]], ["sem dono"])
        self.assertEqual(self.request("GET", "/api/tasks/assignees")[1]["assignees"], [{"name": "Bruno", "open": 1, "total": 1}])
