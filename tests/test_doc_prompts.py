import os
import unittest
from pathlib import Path

from vulcan_celox.core.doc_prompts import (GENERAL_SYSTEM, SESSION_SYSTEM, SessionEntry, general_doc_prompt,
                                              relative_link, session_doc_prompt)
from vulcan_celox.core.models import Note, Tag, Task
from vulcan_celox.core.sessions import SessionRecord

TAGS = {"t1": Tag(id="t1", name="deploy", color="#6ea8fe")}


def record(i=1, commands=None):
    return SessionRecord(id=f"{i:012x}", title=f"sessão {i}", site="loja",
                         cwd=os.path.join(os.path.expanduser("~"), "Lerd", "loja"), tags=["t1"],
                         commands=commands if commands is not None else [{"ts": "2026-09-14T10:00:00Z", "cmd": "php artisan migrate"}],
                         created_at="2026-09-14T10:00:00Z", closed_at="2026-09-14T10:20:00Z", exit_code=0)


class SessionPromptTest(unittest.TestCase):
    def test_conteudo_mascarado_e_limite(self):
        rec = record(commands=[{"ts": "2026-09-14T10:01:00Z", "cmd": "export DB_PASSWORD=segredo123"},
                               {"ts": "2026-09-14T10:02:00Z", "cmd": "php artisan migrate"}])
        tasks = [Task(title="Rodar seeders", status="doing", tags=["t1"]), Task(title="Criar índice", due="2026-09-20")]
        notes = [Note(text="Usar fila redis")]
        transcript = "x" * 70_000 + "\nMigrated: 2026_09_14_create_orders"
        prompt = session_doc_prompt(rec, tasks, notes, TAGS, transcript, limit=60_000)
        self.assertEqual(prompt.system, SESSION_SYSTEM)
        for expected in ("php artisan migrate", "[fazendo] Rodar seeders", "(prazo 2026-09-20)", "Usar fila redis",
                         "Tags da sessão: deploy", "Migrated: 2026_09_14_create_orders", "últimos 60000 caracteres",
                         "Pasta: " + os.path.join("~", "Lerd", "loja")):
            self.assertIn(expected, prompt.user)
        self.assertNotIn("segredo123", prompt.user)
        self.assertNotIn(os.path.expanduser("~") + "/Lerd", prompt.user)
        self.assertEqual(prompt.redactions, 1)
        self.assertTrue(prompt.truncated)
        self.assertLess(len(prompt.user), 65_000)
        self.assertIn("travessão", prompt.system)

    def test_cerca_do_registro_nao_quebra(self):
        prompt = session_doc_prompt(record(), [], [], TAGS, "saída com ``` no meio")
        self.assertEqual(prompt.user.count("```"), 2)


class GeneralPromptTest(unittest.TestCase):
    def test_orcamento_com_200_sessoes(self):
        entries = []
        for i in range(200):
            rec = record(i, commands=[{"ts": "2026-09-14T10:00:00Z", "cmd": f"comando longo {i} " + "y" * 200}] * 40)
            doc = "# Doc\n" + "z" * 5000 if i % 3 == 0 else None
            entries.append(SessionEntry(rec, [Task(title=f"tarefa {i}")], [Note(text="nota " * 100)],
                                        f"sessoes/loja/s{i}.md", doc))
        prompt = general_doc_prompt(entries, TAGS, budget=120_000)
        self.assertEqual(prompt.system, GENERAL_SYSTEM)
        self.assertLessEqual(len(prompt.user), 120_000 + 200 * 120)
        self.assertTrue(prompt.truncated)
        self.assertGreater(prompt.stats["detailed"], 10)
        self.assertIn("[sessão 199](sessoes/loja/s199.md)", prompt.user)
        self.assertIn("Documentação da sessão:", prompt.user)

    def test_link_relativo(self):
        base = Path("/tmp/dados")
        self.assertEqual(relative_link("/tmp/dados/sessoes/loja/a.md", base), "sessoes/loja/a.md")
        self.assertEqual(relative_link(None, base), "")
