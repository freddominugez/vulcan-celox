"""Unified agent history with content search, and the agents block of --doctor."""

import json
import shutil

from tests.helpers import FIXTURES, TempDirTestCase
from tests import test_agents_api
from vulcan_celox.core.agents import status
from vulcan_celox.core.agents.history import MARK_CLOSE, MARK_OPEN
from vulcan_celox.core.agents.index import SCHEMA_VERSION, AgentIndex
from vulcan_celox.core.agents.watcher import AgentWatcher
from vulcan_celox.core.doctor import collect

CODEX_SID = "019a0000-1111-7222-8333-444444444444"
FRETE_SID = "33333333-4444-4555-8666-777777777777"


def frete_session(path):
    lines = [
        {"type": "user", "timestamp": "2026-10-29T09:00:00Z", "cwd": "/Users/dev/loja", "gitBranch": "fix/frete",
         "message": {"role": "user", "content": "O cálculo do frete arredonda errado no checkout"}},
        {"type": "assistant", "timestamp": "2026-10-29T09:01:00Z", "message": {
            "id": "a1", "usage": {}, "content": [
                {"type": "text", "text": "O arredondamento acontece antes de somar o seguro."},
                {"type": "tool_use", "name": "Edit", "input": {"file_path": "/Users/dev/loja/app/Services/FreteService.php"}},
                {"type": "tool_use", "name": "Bash", "input": {"command": "php artisan test --filter=Frete"}}]}},
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in lines), encoding="utf-8")


class HistoryTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        shutil.copytree(FIXTURES / "agents" / "claude", self.tmp / "claude")
        shutil.copytree(FIXTURES / "agents" / "codex", self.tmp / "codex")
        self.frete = self.tmp / "claude" / "projects" / "-Users-dev-loja" / f"{FRETE_SID}.jsonl"
        frete_session(self.frete)
        self.env = {"CLAUDE_CONFIG_DIR": str(self.tmp / "claude"), "CODEX_HOME": str(self.tmp / "codex"), "HOME": str(self.tmp)}
        self.db_path = self.tmp / "dados" / "agentes.db"
        self.index = AgentIndex(self.db_path)
        AgentWatcher(self.index, self.env).run_once()

    def tearDown(self):
        self.index.close()
        super().tearDown()

    def test_busca_ignora_acento_e_caixa(self):
        self.assertTrue(self.index.fts)
        for q in ("calculo", "CÁLCULO", "cálc"):
            with self.subTest(q=q):
                hits = self.index.search(q)
                self.assertEqual([(h["session_id"], h["kind"]) for h in hits], [(FRETE_SID, "user")])
                self.assertIn(MARK_OPEN + "cálculo" + MARK_CLOSE, hits[0]["text"])

    def test_varias_palavras_sao_todas_exigidas(self):
        self.assertEqual(len(self.index.search("frete checkout")), 1)
        self.assertEqual(self.index.search("frete inexistentezzz"), [])

    def test_filtros_por_tipo_agente_e_projeto(self):
        kinds = {h["kind"] for h in self.index.search("frete")}
        self.assertEqual(kinds, {"user", "file", "command"})
        self.assertEqual({h["kind"] for h in self.index.search("frete", kind="comandos")}, {"command"})
        self.assertEqual({h["kind"] for h in self.index.search("frete", kind="arquivos")}, {"file"})
        self.assertEqual(self.index.search("frete", agent="codex"), [])
        self.assertTrue(all(h["project"] == "clerk" for h in self.index.search("", agent="codex")))
        self.assertTrue(all(h["project"] == "loja" for h in self.index.search("", project="loja")))

    def test_sem_texto_lista_os_mais_recentes(self):
        hits = self.index.search("", limit=5)
        self.assertEqual(len(hits), 5)
        self.assertEqual([h["at"] for h in hits], sorted((h["at"] for h in hits), reverse=True))

    def test_jsonl_apagado_continua_pesquisavel(self):
        self.frete.rename(self.tmp / "apagado.jsonl")
        AgentWatcher(self.index, self.env).run_once()
        self.assertEqual(self.index.search("seguro")[0]["session_id"], FRETE_SID)

    def test_reserva_like_sem_fts5(self):
        self.index.fts = False
        hits = self.index.search("arredondamento")
        self.assertEqual([h["kind"] for h in hits], ["assistant"])
        self.assertIn(MARK_OPEN + "arredondamento" + MARK_CLOSE, hits[0]["text"])

    def test_indice_antigo_ganha_a_tabela_de_busca(self):
        self.index.db.executescript("DROP TRIGGER events_history_ai; DROP TRIGGER events_history_ad; DROP TABLE history;"
                                    "UPDATE meta SET value='1' WHERE key='schema_version';")
        self.index.close()
        self.index = AgentIndex(self.db_path)
        AgentWatcher(self.index, self.env).run_once()  # old schema: the index is re-read
        self.assertEqual(self.index.search("seguro")[0]["session_id"], FRETE_SID)
        version = self.index.db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
        self.assertEqual(version, str(SCHEMA_VERSION))

    def test_reconstruir_esvazia_a_busca(self):
        self.index.rebuild()
        self.assertEqual(self.index.search("frete"), [])
        AgentWatcher(self.index, self.env).run_once()
        self.assertEqual(len(self.index.search("calculo")), 1)

    def test_status_e_doctor(self):
        (self.tmp / "claude" / "settings.json").write_text(json.dumps({"cleanupPeriodDays": 90}))
        (self.tmp / "codex" / "sessions" / "x.jsonl.zst").write_bytes(b"z")
        self.env["VULCAN_ZSTD_BIN"] = ""  # without the command: ignored and counted (with it: tests/test_codex_zst.py)
        info = status.collect(self.env, self.tmp / "dados")
        self.assertEqual(info["claude_cleanup"], {"days": 90, "configured": True})
        self.assertEqual((info["claude_session_files"], info["codex_session_files"], info["codex_zst_ignored"]), (2, 1, 1))
        self.assertEqual(info["indexed"]["claude"], 2)
        self.assertTrue(info["fts5"])
        env = {**self.env, "VULCAN_CELOX_HOME": str(self.tmp / "dados"), "VULCAN_VALET_BIN": str(self.tmp / "x"),
               "VULCAN_LERD_BIN": str(self.tmp / "x"), "VULCAN_LERD_API": "http://127.0.0.1:1"}
        self.assertIn("agents", collect(env))

    def test_cleanup_padrao_e_settings_invalido(self):
        self.assertEqual(status.claude_cleanup_days(self.tmp / "claude"), {"days": 30, "configured": False})
        (self.tmp / "claude" / "settings.json").write_text("{nao e json")
        self.assertEqual(status.claude_cleanup_days(self.tmp / "claude"), {"days": 30, "configured": False})


class HistoryApiTest(test_agents_api.AgentsServerCase):
    """Reuses the server with fixtures from the routes test; only the history routes."""

    def test_rota_de_historico(self):
        data = self.get("/api/agents/history?q=frete&kind=pedidos")
        self.assertTrue(data["fts"])
        self.assertEqual({h["kind"] for h in data["hits"]}, {"user"})
        self.assertEqual(data["claude_cleanup"]["days"], 30)
        status_code, _, _ = self.request("GET", "/api/agents/history?kind=tudo-errado")
        self.assertEqual(status_code, 400)
        self.assertEqual({h["agent"] for h in self.get("/api/agents/history?agent=codex&limit=3")["hits"]}, {"codex"})
