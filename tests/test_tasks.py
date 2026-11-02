from tests.helpers import TempDirTestCase
from vulcan_terminal.core.notebook import ALL, InvalidDue, Notebook
from vulcan_terminal.core.store import Store


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class TasksTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.clock = FakeClock()
        self.nb = Notebook(Store(self.tmp), clock=self.clock)

    def test_ciclo_de_status_e_done_at(self):
        t = self.nb.add_task("loja", "publicar")
        self.assertEqual(self.nb.cycle_status(t.id).status, "doing")
        self.assertIsNone(t.done_at)
        self.assertEqual(self.nb.cycle_status(t.id).status, "done")
        self.assertIsNotNone(t.done_at)
        stamp = t.done_at
        self.nb.set_status(t.id, "done")
        self.assertEqual(t.done_at, stamp)
        self.nb.set_status(t.id, "todo")
        self.assertIsNone(t.done_at)
        with self.assertRaises(ValueError):
            self.nb.set_status(t.id, "feito")

    def test_prazo_invalido(self):
        for due in ("2026-13-40", "2026-02-30", "13/09/2026", "2026-9-1"):
            with self.assertRaises(InvalidDue, msg=due):
                self.nb.add_task(None, "x", due=due)
        t = self.nb.add_task(None, "x", due="2026-09-30")
        self.assertEqual(t.due, "2026-09-30")
        self.nb.update_task(t.id, due="")
        self.assertIsNone(t.due)

    def test_titulo_e_prioridade(self):
        with self.assertRaises(ValueError):
            self.nb.add_task(None, "   ")
        with self.assertRaises(ValueError):
            self.nb.add_task(None, "x", priority=7)
        t = self.nb.add_task(None, "x", priority=3)
        self.assertEqual(self.nb.cycle_priority(t.id).priority, 1)

    def test_filtro_status_e_tag(self):
        bug = self.nb.create_tag("Bug")
        a = self.nb.add_task("loja", "a", tags=[bug.id])
        b = self.nb.add_task("loja", "b", tags=[bug.id])
        c = self.nb.add_task("blog", "c", tags=[bug.id])
        d = self.nb.add_task("loja", "d")
        for t in (a, c, d):
            self.nb.set_status(t.id, "done")
        self.assertEqual(self.nb.filter_tasks(ALL, ["done"], bug.id), [a, c])
        self.assertEqual(self.nb.filter_tasks("loja", ["done"], bug.id), [a])
        self.assertEqual(self.nb.filter_tasks("loja", ["todo"]), [b])
        self.assertEqual(len(self.nb.filter_tasks(None)), 0)

    def test_ordenacao(self):
        x = self.nb.add_task(None, "x", priority=2, due="2026-10-01")
        y = self.nb.add_task(None, "y", priority=1)
        z = self.nb.add_task(None, "z", priority=2, due="2026-09-20")
        self.assertEqual(self.nb.filter_tasks(None, sort="priority"), [y, z, x])
        self.assertEqual(self.nb.filter_tasks(None, sort="due"), [z, x, y])
        self.assertEqual(self.nb.filter_tasks(None, sort="manual"), [x, y, z])
        self.nb.move_task(z.id, -2)
        self.assertEqual(self.nb.filter_tasks(None, sort="manual"), [z, x, y])

    def test_desfazer_exclusao(self):
        a = self.nb.add_task(None, "a")
        b = self.nb.add_task(None, "b")
        self.nb.delete_task(a.id)
        self.clock.now += 4.9
        self.assertIs(self.nb.undo_delete(), a)
        self.assertEqual(self.nb.tasks, [a, b])
        self.assertEqual(len(Notebook(Store(self.tmp)).tasks), 2)

        self.nb.delete_task(b.id)
        self.clock.now += 5.1
        self.assertIsNone(self.nb.undo_delete())
        self.assertEqual(self.nb.tasks, [a])
