import unittest

from tests.helpers import TempDirTestCase
from vulcan_terminal.core.models import Task
from vulcan_terminal.core.notebook import Notebook
from vulcan_terminal.core.progress import Progress, progress, progress_by_site, progress_by_tag, text_bar
from vulcan_terminal.core.store import Store


def tasks(done, total, site=None, tags=()):
    return [Task(site=site, title=str(i), status="done" if i < done else "todo", tags=list(tags))
            for i in range(total)]


class ProgressTest(unittest.TestCase):
    def test_tabela(self):
        casos = [((0, 0), 0, "sem tarefas"), ((3, 12), 25, "3/12 · 25%"), ((12, 12), 100, "12/12 · 100%"),
                 ((1, 3), 33, "1/3 · 33%"), ((2, 3), 67, "2/3 · 67%"), ((7, 12), 58, "7/12 · 58%"),
                 ((1, 8), 13, "1/8 · 13%")]
        for (done, total), pct, label in casos:
            p = progress(tasks(done, total))
            self.assertEqual((p.pct, p.label), (pct, label), (done, total))

    def test_doing_e_todo(self):
        items = tasks(1, 4)
        items[1].status = "doing"
        p = progress(items)
        self.assertEqual((p.done, p.doing, p.todo), (1, 1, 2))
        self.assertEqual(Progress().short, "")

    def test_por_site_e_tag(self):
        items = tasks(1, 2, site="loja", tags=["t1"]) + tasks(0, 3, site=None, tags=["t1", "t2"])
        by_site = progress_by_site(items)
        self.assertEqual(by_site["loja"].label, "1/2 · 50%")
        self.assertEqual(by_site[None].label, "0/3 · 0%")
        by_tag = progress_by_tag(items)
        self.assertEqual((by_tag["t1"].done, by_tag["t1"].total), (1, 5))
        self.assertEqual(by_tag["t2"].total, 3)

    def test_barra_texto(self):
        self.assertEqual(text_bar(58), "█████░░░░░")
        self.assertEqual(text_bar(0), "░" * 10)
        self.assertEqual(text_bar(100), "█" * 10)


class ObservadorTest(TempDirTestCase):
    def test_ui_recebe_evento_e_recalcula(self):
        nb = Notebook(Store(self.tmp))
        seen = []
        nb.subscribe(lambda kind: seen.append((kind, progress(nb.tasks).label)))
        t = nb.add_task("loja", "a")
        nb.set_status(t.id, "done")
        self.assertEqual(seen, [("tasks", "0/1 · 0%"), ("tasks", "1/1 · 100%")])
