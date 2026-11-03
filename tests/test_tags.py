from tests.helpers import TempDirTestCase
from vulcan_celox.core.notebook import DuplicateTag, Notebook, chip_specs
from vulcan_celox.core.store import Store


class TagsTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.nb = Notebook(Store(self.tmp))

    def test_nome_unico_sem_diferenciar_caixa(self):
        self.nb.create_tag("Bug")
        with self.assertRaises(DuplicateTag):
            self.nb.create_tag("bug")
        with self.assertRaises(ValueError):
            self.nb.create_tag("   ")

    def test_excluir_limpa_referencias(self):
        bug = self.nb.create_tag("bug")
        outra = self.nb.create_tag("ux")
        n1 = self.nb.add_note("loja", "a")
        t1 = self.nb.add_task("loja", "b")
        t2 = self.nb.add_task(None, "c")
        for item in (n1, t1, t2):
            self.nb.set_item_tags(item, [bug.id, outra.id])
        self.assertEqual(self.nb.delete_tag(bug.id), 3)
        self.assertTrue(all(i.tags == [outra.id] for i in (n1, t1, t2)))
        reloaded = Notebook(Store(self.tmp))
        self.assertTrue(all(t.tags == [outra.id] for t in reloaded.tasks))
        self.assertNotIn(bug.id, reloaded.tags)

    def test_renomear_preserva_id(self):
        tag = self.nb.create_tag("bgu")
        task = self.nb.add_task(None, "x")
        self.nb.set_item_tags(task, [tag.id])
        self.nb.rename_tag(tag.id, "bug")
        self.assertEqual(self.nb.tags[tag.id].name, "bug")
        self.assertEqual(chip_specs(task, self.nb.tags)[0][1], "bug")
        self.nb.create_tag("ux")
        with self.assertRaises(DuplicateTag):
            self.nb.rename_tag(tag.id, "UX")
        self.nb.rename_tag(tag.id, "BUG")  # mesma tag, só muda a caixa

    def test_chip_specs(self):
        a = self.nb.create_tag("a", "#111111")
        b = self.nb.create_tag("b", "#222222")
        note = self.nb.add_note(None, "x")
        note.tags = [b.id, "orfa", a.id]
        self.assertEqual(chip_specs(note, self.nb.tags),
                         [(b.id, "b", "#222222"), (a.id, "a", "#111111")])

    def test_add_tag_to_item_cria_e_nao_duplica(self):
        task = self.nb.add_task(None, "x")
        t1 = self.nb.add_tag_to_item(task, "deploy")
        t2 = self.nb.add_tag_to_item(task, "Deploy")
        self.assertEqual(t1.id, t2.id)
        self.assertEqual(task.tags, [t1.id])
        self.nb.remove_tag_from_item(task, t1.id)
        self.assertEqual(task.tags, [])
