"""Performance with many heavy sessions, git cache and index pruning."""

import io
import json
import os
import time
from contextlib import redirect_stdout
from unittest import mock

from tests import test_agents_api
from tests.helpers import TempDirTestCase
from vulcan_celox.__main__ import main
from vulcan_celox.core.agents import repos
from vulcan_celox.core.agents.index import AgentIndex, SCHEMA_VERSION
from vulcan_celox.core.agents.model import AgentSession, CommandRun, FileTouch, SessionEvent
from vulcan_celox.core.runner import FakeRunner, Result

HEAVY_FILES, HEAVY_COMMANDS = 150, 200


def heavy(i, last="2026-10-31T10:00:00Z"):
    root = f"/Users/dev/p{i % 40}"
    return AgentSession(
        id=f"s{i:05d}", agent="claude" if i % 2 else "codex", file_path=f"/x/{i}.jsonl", cwd=root,
        project_root=root, project_name=f"p{i % 40}", git_branch="main", started_at="2026-10-30T09:00:00Z",
        last_activity_at=last, turns=12, commands_total=HEAVY_COMMANDS, published="committed",
        files=[FileTouch(f"{root}/src/arquivo_{k}.php", "edit" if k % 3 else "read", last, last) for k in range(HEAVY_FILES)],
        commands=[CommandRun(f"php artisan test --filter=Caso{k}", last, "test", 0) for k in range(HEAVY_COMMANDS)])


class CargaTest(TempDirTestCase):
    def test_duas_mil_sessoes_pesadas_listam_rapido(self):
        index = AgentIndex(self.tmp / "agentes.db")
        with index.db:
            for i in range(2000):
                s = heavy(i)
                index._write(s, s.file_path, 1.0, 10, 10, {}, [], [])
        index.sessions()  # warms up the SQLite cache
        best = min(self._timed(index.sessions) for _ in range(3))
        self.assertLess(best, 0.1, f"listar 2.000 sessões levou {best:.3f} s")
        listed = index.sessions()
        self.assertEqual(len(listed), 2000)
        self.assertEqual((listed[0].files, listed[0].edited_total(), listed[0].files_total()), ([], 100, 150))
        full = index.session("s00007")
        self.assertEqual((len(full.files), len(full.commands)), (HEAVY_FILES, HEAVY_COMMANDS))
        index.close()

    @staticmethod
    def _timed(fn):
        start = time.perf_counter()
        fn()
        return time.perf_counter() - start

    def test_resumo_antigo_com_listas_continua_legivel(self):
        index = AgentIndex(self.tmp / "agentes.db")
        s = heavy(1)
        with index.db:
            index._write(s, s.file_path, 1.0, 10, 10, {}, [], [])
            index.db.execute("UPDATE sessions SET summary = ? WHERE id = ?", (json.dumps(s.to_dict()), s.id))
        old = index.sessions()[0]
        self.assertEqual((old.edited_total(), old.files_total()), (100, 150))
        index.close()

    def test_indice_antigo_e_reconstruido(self):
        # index created before this change: summaries with the lists inside; an idle session would never be rewritten.
        # Since schema 4 the old index is emptied and re-read, which also removes the lists
        path = self.tmp / "agentes.db"
        index = AgentIndex(path)
        with index.db:
            for i in range(2000):
                s = heavy(i)
                index._write(s, s.file_path, 1.0, 10, 10, {}, [], [])
                index.db.execute("UPDATE sessions SET summary = ? WHERE id = ?", (json.dumps(s.to_dict()), s.id))
            index.db.execute("UPDATE meta SET value = '2' WHERE key = 'schema_version'")
        index.close()
        index = AgentIndex(path)  # opening rebuilds
        version = index.db.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0]
        self.assertEqual(version, str(SCHEMA_VERSION))
        self.assertEqual(index.sessions(), [])
        index.close()

    def test_cache_do_git_nao_repete_em_30_segundos(self):
        runner = FakeRunner(default=Result(0, "true\n"))
        now = [1000.0]
        cache = repos.GitCache(runner, ttl=30, clock=lambda: now[0])
        sessions = [heavy(i) for i in range(40)]  # 40 sessions in 20 projects... 40 distinct roots
        repos.build(sessions, cache)
        calls = len(runner.calls)
        repos.build(sessions, cache)
        self.assertEqual(len(runner.calls), calls)  # everything from the cache
        now[0] += 31
        repos.build(sessions, cache)
        self.assertEqual(len(runner.calls), 2 * calls)
        cache.clear()
        repos.build(sessions, cache)
        self.assertEqual(len(runner.calls), 3 * calls)

    def test_poda_apaga_eventos_antigos_e_mantem_o_resumo(self):
        index = AgentIndex(self.tmp / "agentes.db")
        old, new = heavy(1, "2026-01-10T10:00:00Z"), heavy(2, "2026-10-30T10:00:00Z")
        events = [SessionEvent("2026-01-10T10:00:00Z", "user", f"pedido {k} sobre frete") for k in range(50)]
        with index.db:
            index._write(old, old.file_path, 1.0, 10, 10, {}, events, [])
            index._write(new, new.file_path, 1.0, 10, 10, {}, events, [])
        now = time.mktime((2026, 10, 31, 12, 0, 0, 0, 0, -1))
        self.assertEqual(index.prune_events(180, now=now), 50)
        self.assertEqual(index.events(old.id)[0], [])
        self.assertEqual(len(index.events(new.id, 0, 100)[0]), 50)
        kept = index.session(old.id)
        self.assertEqual((kept.turns, len(kept.files), len(kept.commands)), (12, HEAVY_FILES, HEAVY_COMMANDS))
        self.assertEqual({h["session_id"] for h in index.search("frete")}, {new.id})  # the search follows along
        index.close()

    def test_opcao_podar_agentes(self):
        env = {"VULCAN_CELOX_HOME": str(self.tmp / "home")}
        out = io.StringIO()
        with mock.patch.dict(os.environ, env), redirect_stdout(out):
            self.assertEqual(main(["--podar-agentes", "30"]), 0)
        data = json.loads(out.getvalue())
        self.assertEqual((data["days"], data["events_removed"]), (30, 0))
        with mock.patch.dict(os.environ, env), redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--podar-agentes", "0"]), 2)


class RepoRouteCacheTest(test_agents_api.AgentsServerCase):
    def test_rota_usa_cache_e_atualizar_ignora(self):
        self.get("/api/agents/repos")
        calls = len(self.fake.calls)
        self.get("/api/agents/repos")
        self.assertEqual(len(self.fake.calls), calls)
        self.get("/api/agents/repos?fresh=1")
        self.assertGreater(len(self.fake.calls), calls)
