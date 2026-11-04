from tests.helpers import TempDirTestCase
from vulcan_celox.core.debounce import Debouncer
from vulcan_celox.core.notebook import Notebook
from vulcan_celox.core.store import Store


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class NotesTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.nb = Notebook(Store(self.tmp))

    def test_ordem_fixadas_primeiro(self):
        a = self.nb.add_note("loja", "a")
        b = self.nb.add_note("loja", "b")
        c = self.nb.add_note("loja", "c")
        self.nb.add_note(None, "global")
        self.nb.update_note(c.id, pinned=True)
        self.assertEqual([n.text for n in self.nb.notes_for("loja")], ["c", "a", "b"])
        self.assertEqual([n.text for n in self.nb.notes_for(None)], ["global"])
        self.assertIn(a, self.nb.notes_for("loja"))
        self.assertIn(b, self.nb.notes_for("loja"))

    def test_reorder_persiste(self):
        notes = [self.nb.add_note("loja", t) for t in "abcd"]
        self.nb.reorder_note(notes[3].id, 0)
        self.assertEqual([n.text for n in self.nb.notes_for("loja")], list("dabc"))
        self.nb.reorder_note(notes[3].id, 99)
        reloaded = Notebook(Store(self.tmp))
        self.assertEqual([n.text for n in reloaded.notes_for("loja")], list("abcd"))

    def test_reorder_relativo_na_lista_filtrada(self):
        # the session shows only b and d; dragging d above b must put d before b across the whole site
        notes = {x: self.nb.add_note("loja", x, terminal="s1" if x in "bd" else None) for x in "abcd"}
        self.nb.reorder_note(notes["d"].id, target_id=notes["b"].id)
        self.assertEqual([n.text for n in self.nb.notes_for("loja")], list("adbc"))
        self.assertEqual([n.text for n in self.nb.notes_for("loja", terminal="s1")], list("db"))
        self.nb.reorder_note(notes["a"].id, target_id=notes["c"].id)  # downwards: ends up after the target
        self.assertEqual([n.text for n in self.nb.notes_for("loja")], list("dbca"))
        other = self.nb.add_note(None, "global")
        with self.assertRaises(KeyError):
            self.nb.reorder_note(notes["a"].id, target_id=other.id)

    def test_busca_sem_acento_e_caixa(self):
        self.nb.add_note("loja", "Configurar NGINX no servidor")
        self.nb.add_note("loja", "Ação pendente: revisão")
        self.nb.add_note("loja", "outra coisa")
        self.assertEqual([n.text for n in self.nb.notes_for("loja", "nginx")],
                         ["Configurar NGINX no servidor"])
        self.assertEqual(len(self.nb.notes_for("loja", "acao")), 1)
        self.assertEqual(len(self.nb.notes_for("loja", "REVISAO")), 1)

    def test_filtro_por_tag(self):
        n1 = self.nb.add_note("loja", "a")
        self.nb.add_note("loja", "b")
        tag = self.nb.add_tag_to_item(n1, "infra")
        self.assertEqual(self.nb.notes_for("loja", tag_id=tag.id), [n1])

    def test_cor_cicla_e_exclui(self):
        n = self.nb.add_note(None, "x")
        self.assertEqual(self.nb.cycle_note_color(n.id).color, "rosa")
        self.nb.update_note(n.id, color="preto")
        self.assertEqual(n.color, "rosa")
        self.nb.delete_note(n.id)
        self.assertEqual(Notebook(Store(self.tmp)).notes, [])

    def test_debounce_uma_gravacao(self):
        clock = FakeClock()
        saves = []
        deb = Debouncer(0.5, lambda: saves.append(clock.now), clock=clock)
        for _ in range(3):
            deb.touch()
            clock.now += 0.033
        self.assertFalse(deb.poll())
        clock.now += 0.3
        self.assertFalse(deb.poll())
        clock.now += 0.2
        self.assertTrue(deb.poll())
        self.assertFalse(deb.poll())
        self.assertEqual(len(saves), 1)
        self.assertFalse(deb.flush())
        deb.touch()
        self.assertTrue(deb.flush())
        self.assertEqual(len(saves), 2)
