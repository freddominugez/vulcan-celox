"""Índice de agentes sem bloqueio."""

import json
import os
import threading
import time
from unittest import mock

from tests import test_agents_api
from tests.helpers import TempDirTestCase
from vulcan_terminal.core.agents import index as index_mod
from vulcan_terminal.core.agents import status
from vulcan_terminal.core.agents.index import AgentIndex
from vulcan_terminal.core.agents.watcher import AgentWatcher
from vulcan_terminal.server.agents_api import BoundedCache

SID = "aaaaaaaa-1111-4222-8333-444444444444"


def line(text, n):
    return json.dumps({"type": "user", "timestamp": f"2026-10-31T10:00:{n:02d}Z", "cwd": "/r/loja",
                       "message": {"content": text}}) + "\n"


class IndiceTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.folder = self.tmp / "claude" / "projects" / "-r-loja"
        self.folder.mkdir(parents=True)
        self.file = self.folder / f"{SID}.jsonl"
        self.index = AgentIndex(self.tmp / "dados" / "agentes.db")

    def tearDown(self):
        self.index.close()
        super().tearDown()

    def texts(self):
        rows = self.index.db.execute("SELECT text FROM events WHERE session_id = ? AND kind = 'user' ORDER BY id",
                                     (SID,)).fetchall()
        return [r[0] for r in rows]

    def test_revisao_responde_durante_leitura_lenta(self):
        self.file.write_text("".join(line(f"p{i}", i) for i in range(3)))
        real = index_mod.read_session

        def slow(*args, **kwargs):
            time.sleep(1.0)
            return real(*args, **kwargs)

        with mock.patch.object(index_mod, "read_session", slow):
            worker = threading.Thread(target=self.index.update_file, args=("claude", self.file))
            worker.start()
            time.sleep(0.2)  # a leitura já começou
            started = time.monotonic()
            self.index.revision()
            self.index.sessions()
            elapsed = time.monotonic() - started
            worker.join()
        self.assertLess(elapsed, 0.3, f"revision esperou a leitura do arquivo: {elapsed:.2f}s")
        self.assertEqual(self.texts(), ["p0", "p1", "p2"])

    def test_arquivo_trocado_por_outro_maior_e_relido(self):
        self.file.write_text("".join(line(f"a{i}", i) for i in range(3)))
        self.index.update_file("claude", self.file)
        replacement = self.folder / "novo.tmp"
        replacement.write_text("".join(line(f"b{i}", i) for i in range(6)))
        os.replace(replacement, self.file)  # outro inode, maior que o offset salvo
        self.index.update_file("claude", self.file)
        self.assertEqual(self.texts(), [f"b{i}" for i in range(6)])

    def test_reset_nao_duplica_parse_errors(self):
        self.file.write_text("{ruim\n" + line("a", 1) + line("b", 2))
        self.index.update_file("claude", self.file)
        self.file.write_text("{ruim\n")  # menor: relê do zero
        self.index.update_file("claude", self.file)
        count = self.index.db.execute("SELECT COUNT(*) FROM parse_errors WHERE file_path = ?",
                                      (str(self.file),)).fetchone()[0]
        self.assertEqual(count, 1)

    def test_erro_do_observador_aparece_no_doctor(self):
        self.file.write_text(line("a", 1))
        env = {"CLAUDE_CONFIG_DIR": str(self.tmp / "claude"), "CODEX_HOME": str(self.tmp / "codex"), "HOME": str(self.tmp)}
        watcher = AgentWatcher(self.index, env)
        with mock.patch.object(self.index, "update_file", side_effect=RuntimeError("disco sumiu")):
            watcher.run_once()
        self.assertIn("disco sumiu", watcher.last_error)
        self.assertIn("disco sumiu", self.index.last_error() or "")
        info = status.collect(env, data_dir=self.tmp / "dados")
        self.assertIn("disco sumiu", info["last_error"] or "")

    def test_observador_esquece_arquivo_removido(self):
        self.file.write_text(line("a", 1))
        env = {"CLAUDE_CONFIG_DIR": str(self.tmp / "claude"), "CODEX_HOME": str(self.tmp / "codex"), "HOME": str(self.tmp)}
        watcher = AgentWatcher(self.index, env)
        watcher.run_once()
        self.assertIn(str(self.file), watcher._seen)
        self.file.unlink()
        watcher.run_once()
        self.assertNotIn(str(self.file), watcher._seen)


class CacheTest(TempDirTestCase):
    def test_cache_limitado_e_seguro_entre_threads(self):
        cache = BoundedCache(limit=50)

        def fill(start):
            for i in range(start, start + 200):
                cache.put(f"k{i}", i)
                cache.get(f"k{i - 3}")

        threads = [threading.Thread(target=fill, args=(n * 1000,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertLessEqual(len(cache), 50)
        cache.put("x", 1)
        self.assertEqual(cache.get("x"), 1)


class RevisaoApiTest(test_agents_api.AgentsServerCase):
    def test_erro_do_observador_na_revisao(self):
        self.assertIsNone(self.get("/api/agents/revision")["last_error"])
        self.app.agents.watcher._error("rollout.jsonl: PermissionError: negado")
        self.assertIn("PermissionError", self.get("/api/agents/revision")["last_error"])
