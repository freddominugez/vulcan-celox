import re

from tests.helpers import TempDirTestCase
from vulcan_terminal.core.models import Note, Tag, Task, now_iso
from vulcan_terminal.core.notebook import Notebook
from vulcan_terminal.core.store import Store


class ModelsTest(TempDirTestCase):
    def test_roundtrip(self):
        for obj in (Tag(name="bug", color="#fff"),
                    Note(site="loja", text="oi", color="rosa", tags=["t1"], pinned=True, order=3),
                    Task(site=None, title="deploy", status="doing", priority=1, tags=["t"], due="2026-10-01")):
            self.assertEqual(type(obj).from_dict(obj.to_dict()), obj)

    def test_from_dict_vazio_usa_defaults(self):
        for cls in (Tag, Note, Task):
            obj = cls.from_dict({})
            self.assertTrue(re.fullmatch(r"[0-9a-f]{32}", obj.id))
        self.assertEqual(Task.from_dict({}).status, "todo")
        self.assertIsNone(Note.from_dict(None).site)

    def test_from_dict_tolerante(self):
        task = Task.from_dict({"status": "xpto", "priority": "9", "tags": ["a", 3], "extra": 1})
        self.assertEqual((task.status, task.priority, task.tags), ("todo", 3, ["a"]))
        self.assertEqual(Note.from_dict({"color": "preto"}).color, "amarelo")

    def test_cor_de_tag_antiga_migra(self):
        from vulcan_terminal.core.models import LEGACY_TAG_COLORS, TAG_COLORS
        self.assertEqual(Tag.from_dict({"name": "x", "color": LEGACY_TAG_COLORS[2]}).color, TAG_COLORS[2])
        self.assertEqual(Tag.from_dict({"name": "x", "color": "#123456"}).color, "#123456")

    def test_timestamp_iso_utc(self):
        self.assertTrue(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", now_iso()))

    def test_titulo_da_nota(self):
        self.assertEqual(Note(text="\n  Título aqui \ncorpo").title, "Título aqui")


class NotebookBasicoTest(TempDirTestCase):
    def test_persistencia(self):
        nb = Notebook(Store(self.tmp))
        nb.add_note("loja", "a")
        nb.add_task(None, " revisar ")
        nb2 = Notebook(Store(self.tmp))
        self.assertEqual([n.text for n in nb2.notes], ["a"])
        self.assertEqual([t.title for t in nb2.tasks], ["revisar"])

    def test_observador(self):
        nb = Notebook(Store(self.tmp))
        events = []
        unsubscribe = nb.subscribe(events.append)
        nb.add_task("loja", "x")
        unsubscribe()
        nb.add_note("loja", "y")
        self.assertEqual(events, ["tasks"])

    def test_migracao_post_its_legado(self):
        store = Store(self.tmp)
        store.save("legacy_notes", {
            "loja": [{"texto": "a", "cor": "rosa"}, {"texto": "b", "cor": "azul"}],
            "blog": [{"texto": "c", "cor": "verde"}, {"texto": "d", "cor": "inexistente"}],
        })
        nb = Notebook(store)
        self.assertEqual(nb.migrate_legacy_notes(), 4)
        self.assertEqual(len(nb.notes), 4)
        by_text = {n.text: n for n in nb.notes}
        self.assertEqual((by_text["a"].site, by_text["a"].color), ("loja", "rosa"))
        self.assertEqual(by_text["d"].color, "amarelo")
        tag_names = {nb.tags[t].name for n in nb.notes for t in n.tags}
        self.assertEqual(tag_names, {"loja", "blog"})

        self.assertEqual(Notebook(store).migrate_legacy_notes(), 0)
        self.assertEqual(len(Notebook(store).notes), 4)
