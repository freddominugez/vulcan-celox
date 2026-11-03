"""Índice sqlite das sessões de agente e observação incremental das pastas."""

import json
import os
import shutil
import sqlite3
import time
from datetime import datetime, timezone

from tests.helpers import FIXTURES, TempDirTestCase
from vulcan_terminal.__main__ import main
from vulcan_terminal.core.agents.index import AgentIndex, is_active
from vulcan_terminal.core.agents.watcher import AgentWatcher

CLAUDE_SID = "11111111-2222-4333-8444-555555555555"
CODEX_SID = "019a0000-1111-7222-8333-444444444444"


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class AgentIndexTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        shutil.copytree(FIXTURES / "agents" / "claude", self.tmp / "claude")
        shutil.copytree(FIXTURES / "agents" / "codex", self.tmp / "codex")
        self.env = {"CLAUDE_CONFIG_DIR": str(self.tmp / "claude"), "CODEX_HOME": str(self.tmp / "codex"),
                    "HOME": str(self.tmp)}
        self.claude_file = self.tmp / "claude" / "projects" / "-Users-dev-projeto" / f"{CLAUDE_SID}.jsonl"
        self.index = AgentIndex(self.tmp / "dados" / "agentes.db")

    def tearDown(self):
        self.index.close()
        super().tearDown()

    def watcher(self, **kw):
        return AgentWatcher(self.index, self.env, **kw)

    def events(self, sid):
        return self.index.db.execute("SELECT COUNT(*) FROM events WHERE session_id = ?", (sid,)).fetchone()[0]

    def test_indexa_as_duas_fontes(self):
        changed = self.watcher().run_once()
        self.assertEqual(sorted(changed), sorted([CLAUDE_SID, CODEX_SID]))
        self.assertEqual({s.agent for s in self.index.sessions()}, {"claude", "codex"})
        self.assertEqual(self.index.session(CODEX_SID).project_name, "clerk")
        self.assertGreater(self.events(CLAUDE_SID), 0)
        files = self.index.db.execute("SELECT COUNT(*) FROM session_files WHERE session_id = ?", (CLAUDE_SID,)).fetchone()[0]
        self.assertEqual(files, 13)

    def test_crescer_reindexa_so_o_novo_sem_duplicar(self):
        w = self.watcher()
        w.run_once()
        before = self.index.session(CLAUDE_SID)
        ev_before = self.events(CLAUDE_SID)
        rev = self.index.revision()
        self.assertEqual(w.run_once(), [])  # nada mudou: nada relido
        self.assertEqual(self.index.revision(), rev)
        with self.claude_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "timestamp": "2026-10-31T09:00:00Z", "cwd": "/Users/dev/projeto",
                                "message": {"role": "user", "content": "pedido novo"}}) + "\n")
            f.write(json.dumps({"type": "assistant", "timestamp": "2026-10-31T09:00:05Z", "message": {
                "id": "msg-novo", "model": "claude-opus-5-5", "usage": {"input_tokens": 1, "output_tokens": 2},
                "content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": "/Users/dev/projeto/CLAUDE.md"}}]}}) + "\n")
        self.assertEqual(w.run_once(), [CLAUDE_SID])
        after = self.index.session(CLAUDE_SID)
        self.assertEqual(after.turns, before.turns + 1)
        self.assertEqual(len(after.files), len(before.files))
        self.assertEqual(after.tokens["output"], before.tokens["output"] + 2)
        self.assertEqual(self.events(CLAUDE_SID), ev_before + 2)
        self.assertGreater(self.index.revision(), rev)

    def test_reconstruir_do_zero_da_o_mesmo_resultado(self):
        self.watcher().run_once()
        first = {s.id: s.to_dict() for s in self.index.sessions()}
        ev = self.events(CLAUDE_SID)
        self.index.rebuild()
        self.assertEqual(self.index.sessions(), [])
        self.watcher().run_once()
        self.assertEqual({s.id: s.to_dict() for s in self.index.sessions()}, first)
        self.assertEqual(self.events(CLAUDE_SID), ev)

    def test_arquivo_que_encolheu_e_relido_sem_duplicar(self):
        w = self.watcher()
        w.run_once()
        data = self.claude_file.read_bytes()
        self.claude_file.write_bytes(data[: len(data) // 2].rsplit(b"\n", 1)[0] + b"\n")
        w.run_once()
        fresh = AgentIndex(self.tmp / "outro.db")
        AgentWatcher(fresh, self.env).run_once()
        self.assertEqual(self.events(CLAUDE_SID), fresh.db.execute("SELECT COUNT(*) FROM events WHERE session_id = ?",
                                                                    (CLAUDE_SID,)).fetchone()[0])
        self.assertEqual(self.index.session(CLAUDE_SID).turns, fresh.session(CLAUDE_SID).turns)
        fresh.close()

    def test_jsonl_apagado_continua_no_indice(self):
        self.watcher().run_once()
        self.claude_file.rename(self.tmp / "fora-do-claude.jsonl")
        self.watcher().run_once()
        self.assertIsNotNone(self.index.session(CLAUDE_SID))

    def codex_file(self, root="codex"):
        return self.tmp / root / "sessions" / "2026" / "10" / "30" / f"rollout-2026-10-30T21-15-44-{CODEX_SID}.jsonl"

    def total_events(self):
        return self.index.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def test_rollout_arquivado_nao_duplica(self):
        self.watcher().run_once()
        before, hits = self.total_events(), len(self.index.search("pedido 1", agent="codex"))
        archived = self.tmp / "codex" / "archived_sessions" / self.codex_file().name
        archived.parent.mkdir(parents=True)
        self.codex_file().rename(archived)
        self.watcher().run_once()
        self.assertEqual(self.total_events(), before)
        self.assertEqual(len(self.index.search("pedido 1", agent="codex")), hits)
        self.assertEqual(self.index.session(CODEX_SID).file_path, str(archived))
        self.assertEqual(self.index.counts()["codex"], 1)

    def test_mesma_sessao_em_duas_raizes_fica_com_a_mais_recente(self):
        shutil.copytree(self.tmp / "codex", self.tmp / "codex2")
        os.utime(self.codex_file("codex"), (1_700_000_000, 1_700_000_000))
        env = {**self.env, "CODEX_HOME": f"{self.tmp / 'codex'},{self.tmp / 'codex2'}"}
        AgentWatcher(self.index, env).run_once()
        first = self.total_events()
        for _ in range(3):  # cada reinício cria um observador novo
            AgentWatcher(self.index, env).run_once()
        self.assertEqual(self.total_events(), first)
        self.assertEqual(self.index.session(CODEX_SID).file_path, str(self.codex_file("codex2")))

    def test_banco_corrompido_vira_corrupt_e_e_recriado(self):
        self.index.close()
        path = self.tmp / "dados" / "agentes.db"
        path.write_bytes(b"isto nao e sqlite" * 100)
        self.index = AgentIndex(path, clock=Clock(1234))
        self.assertEqual(self.index.corrupt_moved.name, "agentes.db.corrupt-1234")
        self.assertTrue(self.index.corrupt_moved.is_file())
        self.assertEqual(self.index.sessions(), [])
        self.watcher().run_once()
        self.assertEqual(len(self.index.sessions()), 2)

    def test_debounce_espera_o_arquivo_parar_de_mudar(self):
        clock = Clock()
        w = self.watcher(clock=clock, debounce=0.3)
        self.assertEqual(w.scan(), 2)
        self.assertEqual(w.poll(), [])
        clock.t += 0.31
        self.assertEqual(sorted(w.poll()), sorted([CLAUDE_SID, CODEX_SID]))

    def test_sessao_ativa_pelo_mtime_e_pelo_ultimo_evento(self):
        clock = Clock(time.time())
        self.index.clock = clock
        os.utime(self.claude_file)  # cópia recém-feita: arquivo novo, eventos antigos
        self.watcher().run_once()
        self.assertFalse(self.index.session(CLAUDE_SID).is_active)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with self.claude_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "timestamp": now, "message": {"content": "continua"}}) + "\n")
        self.watcher().run_once()
        self.assertTrue(self.index.session(CLAUDE_SID).is_active)
        clock.t += 120
        self.assertFalse(self.index.session(CLAUDE_SID).is_active)

    def test_regra_de_sessao_ativa(self):
        now = 1_800_000_000.0
        iso = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")  # noqa: E731
        self.assertTrue(is_active(now - 5, iso(now - 30), now))
        self.assertFalse(is_active(now - 5, iso(now - 86400), now))   # pasta copiada ou restaurada
        self.assertFalse(is_active(now - 300, iso(now - 30), now))    # arquivo parado
        self.assertTrue(is_active(now - 5, "", now))                  # sem data de evento: vale o arquivo
        self.assertFalse(is_active(None, iso(now), now))

    def test_eventos_paginados(self):
        self.watcher().run_once()
        total = self.events(CLAUDE_SID)
        page, nxt = self.index.events(CLAUDE_SID, 0, 50)
        self.assertEqual((len(page), nxt), (50, 50))
        rest, end = self.index.events(CLAUDE_SID, 50, total)
        self.assertEqual((len(rest), end), (total - 50, None))

    def test_thread_do_observador(self):
        changes = []
        w = self.watcher(interval=0.05, debounce=0.01, on_change=changes.extend).start()
        deadline = time.time() + 5
        while len(changes) < 2 and time.time() < deadline:
            time.sleep(0.05)
        w.stop()
        self.assertEqual(sorted(changes), sorted([CLAUDE_SID, CODEX_SID]))
        self.assertIsNone(w.last_error)

    def test_nunca_escreve_nas_pastas_dos_agentes(self):
        before = {p: p.stat().st_mtime for p in (self.tmp / "claude").rglob("*")}
        self.watcher().run_once()
        self.assertEqual(before, {p: p.stat().st_mtime for p in (self.tmp / "claude").rglob("*")})

    def test_opcao_reindexar_agentes(self):
        import io
        from contextlib import redirect_stdout
        from unittest import mock
        env = {**self.env, "VULCAN_TERMINAL_HOME": str(self.tmp / "home")}
        out = io.StringIO()
        with mock.patch.dict(os.environ, env), redirect_stdout(out):
            self.assertEqual(main(["--reindexar-agentes"]), 0)
        data = json.loads(out.getvalue())
        self.assertEqual((data["sessions"], data["counts"]["claude"], data["counts"]["codex"]), (2, 1, 1))
        with sqlite3.connect(str(self.tmp / "home" / "agentes.db")) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 2)
