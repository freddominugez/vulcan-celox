from tests.helpers import TempDirTestCase
from vulcan_celox.core.markdown_index import (BLOCK_END, BLOCK_START, ProjectIndexSettings,
                                                 ProjectPathMissing, apply_block, render_project_block,
                                                 sync_project_indexes, write_project_index)
from vulcan_celox.core.models import Task
from vulcan_celox.core.store import Store

PREFACIO = "# Meu projeto\n\nAnotações escritas à mão.\n\n"
POSFACIO = "\n\n## Rodapé manual\n\nNão mexer.\n"


class ProjectIndexTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.project = self.tmp / "loja"
        self.project.mkdir()
        self.tasks = [Task(site="loja", title="a"), Task(site="blog", title="b"),
                      Task(site="loja", title="c", status="done", done_at="2026-09-13T00:00:00Z")]

    def test_bloco_so_do_site(self):
        block = render_project_block("loja", self.tasks, {})
        self.assertTrue(block.startswith(BLOCK_START) and block.endswith(BLOCK_END))
        self.assertIn("| a |", block)
        self.assertNotIn("| b |", block)
        self.assertIn("1/2 · 50%", block)

    def test_preserva_texto_fora_do_bloco(self):
        target = self.project / "TAREFAS.md"
        target.write_text(PREFACIO + BLOCK_START + "\nvelho\n" + BLOCK_END + POSFACIO, encoding="utf-8")
        for i in range(3):
            self.tasks.append(Task(site="loja", title=f"nova {i}"))
            write_project_index(str(self.project), "loja", self.tasks, {})
        text = target.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(PREFACIO + BLOCK_START))
        self.assertTrue(text.endswith(BLOCK_END + POSFACIO))
        self.assertNotIn("velho", text)
        self.assertIn("nova 2", text)
        self.assertEqual(text.count(BLOCK_START), 1)

    def test_sem_marcadores_acrescenta_ao_final(self):
        self.assertEqual(apply_block("", "B"), "B\n")
        self.assertEqual(apply_block("texto\n\n\n", "B"), "texto\n\nB\n")
        target = self.project / "TAREFAS.md"
        target.write_text("Notas soltas", encoding="utf-8")
        write_project_index(str(self.project), "loja", self.tasks, {})
        text = target.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("Notas soltas\n\n" + BLOCK_START))
        write_project_index(str(self.project), "loja", self.tasks, {})
        self.assertEqual(target.read_text(encoding="utf-8"), text)

    def test_cria_arquivo(self):
        self.assertTrue(write_project_index(str(self.project), "loja", self.tasks, {}))
        self.assertFalse(write_project_index(str(self.project), "loja", self.tasks, {}))

    def test_pasta_inexistente_desliga(self):
        with self.assertRaises(ProjectPathMissing):
            write_project_index(str(self.tmp / "sumiu"), "loja", self.tasks, {})
        settings = ProjectIndexSettings(Store(self.tmp / "home"))
        settings.set("loja", True)
        settings.set("sumiu", True)
        settings.set("fora-da-lista", True)
        warnings = sync_project_indexes(settings, {"loja": str(self.project), "sumiu": str(self.tmp / "x")},
                                        self.tasks, {})
        self.assertEqual(len(warnings), 1)
        self.assertFalse(ProjectIndexSettings(Store(self.tmp / "home")).enabled("sumiu"))
        self.assertTrue(settings.enabled("loja"))
        self.assertTrue(settings.enabled("fora-da-lista"))
        self.assertTrue((self.project / "TAREFAS.md").exists())
