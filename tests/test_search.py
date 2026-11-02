import json

from tests.helpers import TempDirTestCase
from vulcan_terminal.core.notebook import Notebook
from vulcan_terminal.core.search import search
from vulcan_terminal.core.sites import Site
from vulcan_terminal.core.store import Store


class SearchTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.nb = Notebook(Store(self.tmp / "a"))
        self.sites = [Site("loja", "loja.test", "/p/loja", "manual"), Site("nginx-proxy", "nginx-proxy.test", "/p/x", "manual")]

    def test_tipos_e_ranking(self):
        note = self.nb.add_note("loja", "Deploy\nreiniciar o NGINX depois do deploy")
        task = self.nb.add_task("loja", "Configurar nginx")
        exact = self.nb.add_task(None, "nginx")
        self.nb.create_tag("nginx")
        hits = search("NGINX", self.sites, self.nb)
        self.assertEqual([h.kind for h in hits], ["site", "task", "task", "note", "tag"])
        self.assertEqual([h.key for h in hits if h.kind == "task"], [exact.id, task.id])
        note_hit = next(h for h in hits if h.kind == "note")
        self.assertEqual((note_hit.key, note_hit.site, note_hit.title), (note.id, "loja", "Deploy"))
        self.assertIn("NGINX", note_hit.snippet)

    def test_sem_acento_e_vazio(self):
        self.nb.add_task(None, "Revisão de segurança")
        self.assertEqual(len(search("revisao", [], self.nb)), 1)
        self.assertEqual(search("   ", self.sites, self.nb), [])
        self.assertEqual(search("zzz", self.sites, self.nb), [])


class ExportImportTest(TempDirTestCase):
    def _cheio(self, root):
        nb = Notebook(Store(root))
        tag = nb.create_tag("infra")
        nb.set_item_tags(nb.add_task("loja", "a"), [tag.id])
        nb.add_task(None, "b")
        nb.set_item_tags(nb.add_note("loja", "nota"), [tag.id])
        return nb

    def test_export_import_reproduz_ids(self):
        origem = self._cheio(self.tmp / "origem")
        arquivo = self.tmp / "caderno.json"
        self.assertEqual(origem.export(arquivo), {"tags": 1, "notes": 1, "tasks": 2})
        destino = Notebook(Store(self.tmp / "destino"))
        destino.import_(arquivo)
        self.assertEqual({t.id for t in destino.tasks}, {t.id for t in origem.tasks})
        self.assertEqual({n.id for n in destino.notes}, {n.id for n in origem.notes})
        self.assertEqual(set(destino.tags), set(origem.tags))
        self.assertEqual(len(Notebook(Store(self.tmp / "destino")).tasks), 2)

    def test_import_em_cheio_nao_duplica(self):
        origem = self._cheio(self.tmp / "origem")
        arquivo = self.tmp / "caderno.json"
        origem.export(arquivo)
        origem.import_(arquivo)
        origem.import_(arquivo)
        self.assertEqual((len(origem.tasks), len(origem.notes), len(origem.tags)), (2, 1, 1))

    def test_tag_com_mesmo_nome_unifica(self):
        origem = self._cheio(self.tmp / "origem")
        arquivo = self.tmp / "caderno.json"
        origem.export(arquivo)
        outro = Notebook(Store(self.tmp / "outro"))
        local = outro.create_tag("INFRA")
        outro.import_(arquivo)
        self.assertEqual(list(outro.tags), [local.id])
        self.assertTrue(all(t.tags in ([], [local.id]) for t in outro.tasks))

    def test_arquivo_invalido(self):
        ruim = self.tmp / "ruim.json"
        ruim.write_text(json.dumps({"app": "outro"}), encoding="utf-8")
        with self.assertRaises(ValueError):
            Notebook(Store(self.tmp / "x")).import_(ruim)
