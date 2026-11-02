import os

from tests.helpers import GOLDEN, TempDirTestCase
from vulcan_terminal.core.markdown_index import anchor, render_global, write_if_changed
from vulcan_terminal.core.models import Tag, Task

TAGS = {t.id: t for t in (Tag(id="t-infra", name="infra"), Tag(id="t-bug", name="bug"),
                          Tag(id="t-loja", name="loja"), Tag(id="t-conteudo", name="conteúdo"))}


def fixture_tasks():
    return [
        Task(id="1", site="loja", title="Configurar SSL", status="doing", priority=1, tags=["t-infra"],
             due="2026-09-20", order=0),
        Task(id="2", site="loja", title="Publicar | versão 2", status="todo", priority=2, order=1),
        Task(id="3", site="loja", title="Corrigir checkout", status="done", priority=1, tags=["t-bug", "t-loja"],
             order=2, done_at="2026-09-10T12:00:00Z"),
        Task(id="4", site="loja", title="Ajustar layout", status="done", priority=3, order=3,
             done_at="2026-09-11T08:30:00Z"),
        Task(id="5", site="blog", title="Escrever post", status="todo", priority=2, tags=["t-conteudo"],
             due="2026-10-01", order=0),
        Task(id="6", site="blog", title="Revisar SEO", status="todo", priority=3, order=1),
        Task(id="7", site="blog", title="Migrar comentários", status="done", priority=1, tags=["t-bug", "orfa"],
             order=2, done_at="2026-09-12T00:00:00Z"),
    ]


class MarkdownIndexTest(TempDirTestCase):
    def test_golden(self):
        expected = (GOLDEN / "TAREFAS-exemplo.md").read_text(encoding="utf-8")
        self.assertEqual(render_global(fixture_tasks(), TAGS), expected)

    def test_deterministico_independente_da_ordem(self):
        tasks = fixture_tasks()
        self.assertEqual(render_global(tasks, TAGS), render_global(list(reversed(tasks)), TAGS))

    def test_sem_tarefas(self):
        text = render_global([], {})
        self.assertIn("**Progresso geral:** sem tarefas", text)
        self.assertIn("_Sem tarefas._", text)
        self.assertTrue(text.endswith("\n"))

    def test_global_primeiro(self):
        tasks = fixture_tasks() + [Task(site=None, title="Renovar domínio")]
        text = render_global(tasks, TAGS)
        self.assertLess(text.index("- [Global](#global)"), text.index("- [blog](#blog)"))
        self.assertIn("## Global", text)

    def test_ancoras(self):
        self.assertEqual(anchor("Meu Blog"), "meu-blog")
        self.assertEqual(anchor("loja-2"), "loja-2")
        self.assertEqual(anchor("Área (nova)!"), "área-nova")
        self.assertEqual(anchor("site.com.br"), "sitecombr")

    def test_so_grava_quando_muda(self):
        target = self.tmp / "sub" / "TAREFAS.md"
        text = render_global(fixture_tasks(), TAGS)
        self.assertTrue(write_if_changed(target, text))
        before = os.stat(target).st_mtime_ns
        self.assertFalse(write_if_changed(target, text))
        self.assertEqual(os.stat(target).st_mtime_ns, before)
        self.assertTrue(write_if_changed(target, text + "x"))
