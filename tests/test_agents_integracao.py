"""Memória, índice geral, árvore de sessões e documentação com IA mostram o agente pareado."""

from pathlib import Path

from tests import test_agents_api
from tests.helpers import TempDirTestCase
from vulcan_celox.core.agents.model import AgentSession, CommandRun, FileTouch
from vulcan_celox.core.doc_prompts import session_doc_prompt
from vulcan_celox.core.session_memory import render_general_index, render_session_md
from vulcan_celox.core.sessions import SessionRecord

CLAUDE_SID = "11111111-2222-4333-8444-555555555555"
SECRET = "sk-ant-api03-" + "A" * 40


def agent_session():
    return AgentSession(
        id="7f3c9a21", agent="claude", file_path="/x", cwd="/Users/dev/loja", project_root="/Users/dev/loja",
        git_branch="fix/frete", model="claude-opus-5-5", turns=2, published="committed", commands_total=3,
        first_user_message=f"corrija o frete, a chave é {SECRET}",
        files=[FileTouch("/Users/dev/loja/app/Frete.php", "edit"), FileTouch("/Users/dev/loja/config/frete.php", "read")],
        commands=[CommandRun("pytest", kind="test"), CommandRun("pytest", kind="test"), CommandRun("git commit -m x", kind="publish")],
        loop_alert=None, started_at="2026-10-31T10:00:00Z")


class RenderTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.record = SessionRecord(id="aba000000001", title="loja", cwd="/Users/dev/loja", created_at="2026-10-31T09:59:00Z",
                                    commands=[{"ts": "2026-10-31T09:59:30Z", "cmd": "claude"}])

    def test_memoria_com_secao_de_agente_antes_dos_comandos(self):
        text = render_session_md(self.record, [], [], {}, "", agents=[agent_session()])
        self.assertIn("## Sessões de agente (1)", text)
        self.assertIn("### Claude Code · `7f3c9a21`", text)
        self.assertIn("- Arquivos editados (1): `app/Frete.php`", text)
        self.assertIn("- Publicação: commit feito, falta o push", text)
        self.assertIn("- Comandos: 3 (testes: 2)", text)
        self.assertLess(text.index("## Sessões de agente"), text.index("## Comandos executados"))
        self.assertNotIn("## Sessões de agente", render_session_md(self.record, [], [], {}, ""))

    def test_indice_com_coluna_agente(self):
        text = render_general_index([self.record], [], [], {}, self.tmp, {"aba000000001": ["Codex", "Claude Code", "Codex"]})
        self.assertIn("| Comandos | Agente | Tarefas |", text)
        self.assertIn("| 1 | Claude Code, Codex | - |", text)

    def test_texto_para_a_ia_inclui_o_agente_com_segredo_mascarado(self):
        prompt = session_doc_prompt(self.record, [], [], {}, "saída", agents=[agent_session()])
        self.assertIn("## Sessões de agente nesta aba (1)", prompt.user)
        self.assertIn("app/Frete.php", prompt.user)
        self.assertNotIn(SECRET, prompt.user)
        self.assertGreaterEqual(prompt.redactions, 1)


class IntegracaoServidorTest(test_agents_api.AgentsServerCase):
    def setUp(self):
        super().setUp()
        session = self.app.agents.index.session(CLAUDE_SID)
        record = self.app.hub.sessions.create("aba000000001", "projeto", None, "/Users/dev/projeto", theme="oceano")
        record.created_at = session.started_at[:19] + "Z"

    def test_hub_traz_a_sessao_completa_e_a_memoria_mostra(self):
        agents = self.app.hub.agents_for("aba000000001")
        self.assertEqual([s.id for s in agents], [CLAUDE_SID])
        self.assertEqual(len(agents[0].files), 13)
        text = self.app.hub.memory_text(self.app.hub.sessions.get("aba000000001")) or ""
        path = self.app.hub.write_memory("aba000000001")
        self.assertIn("## Sessões de agente (1)", Path(path).read_text(encoding="utf-8"))
        self.assertIsInstance(text, str)

    def test_indice_geral_e_arvore(self):
        self.app.hub.write_index()
        index = (Path(self.app.data_dir) / "INDICE.md").read_text(encoding="utf-8")
        self.assertIn("| Claude Code |", index)
        tree = self.get("/api/sessions/tree")
        node = next(n for n in tree["open"] + tree["closed"] if n["id"] == "aba000000001")
        self.assertEqual(node["theme"], "oceano")
        self.assertEqual(node["agents"], [{"id": CLAUDE_SID, "agent": "claude"}])

    def test_tarefa_criada_a_partir_da_sessao_de_agente_fica_na_aba(self):
        status, data, _ = self.request("POST", "/api/tasks", body={"title": "projeto · main: revisar frete",
                                                                     "terminal": "aba000000001"})
        self.assertEqual(status, 201)
        self.assertEqual(data["terminal"], "aba000000001")
