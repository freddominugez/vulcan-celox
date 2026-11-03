"""Leitura robusta. Linha com tipo inesperado não trava a sessão; datas fora do padrão; sidechain."""

import io
import json
import os
from contextlib import redirect_stdout
from unittest import mock

from tests.helpers import TempDirTestCase
from vulcan_terminal.__main__ import main
from vulcan_terminal.core.agents import claude_reader
from vulcan_terminal.core.agents.index import AgentIndex
from vulcan_terminal.core.agents.model import parse_iso
from vulcan_terminal.core.agents.reading import read_session
from vulcan_terminal.core.agents.watcher import AgentWatcher

GOOD = {"type": "user", "timestamp": "2026-10-31T10:00:00Z", "cwd": "/r", "message": {"role": "user", "content": "oi"}}
HOSTIS_CLAUDE = [
    {"type": "assistant", "timestamp": "2026-10-31T10:00:01Z", "message": {"id": "m1", "model": "x", "usage": {"input_tokens": "n/a"},
                                                                         "content": [{"type": "text", "text": "ok"}]}},
    {"type": "user", "timestamp": 1730000000, "message": {"content": "data numérica"}},
    {"type": "assistant", "timestamp": "2026-10-31T10:00:02Z", "message": {"content": [{"type": "text", "text": None}]}},
    {"type": "user", "timestamp": "2026-10-31T10:00:03Z", "cwd": 123, "gitBranch": ["x"], "message": {"content": "cwd numérico"}},
    {"type": "assistant", "timestamp": "2026-10-31T10:00:04Z", "message": "não é objeto"},
    {"type": "assistant", "timestamp": "2026-10-31T10:00:05Z", "message": {"id": 7, "usage": [], "content": [
        {"type": "tool_use", "name": "Edit", "input": "não é objeto"}, {"type": "tool_use", "name": "Bash", "input": {"command": 5}}]}},
    {"type": "user", "timestamp": None, "message": {"content": [{"type": "text", "text": 9}]}},
]
HOSTIS_CODEX = [
    {"timestamp": "2026-10-31T10:00:00Z", "type": "session_meta", "payload": {"id": 42, "cwd": 7, "git": "main"}},
    {"timestamp": "2026-10-31T10:00:01Z", "type": "turn_context", "payload": {"model": ["x"], "cwd": None}},
    {"timestamp": "2026-10-31T10:00:02Z", "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {
        "input_tokens": "muitos", "cached_input_tokens": None, "output_tokens": 3}}}},
    {"timestamp": "2026-10-31T10:00:03Z", "type": "event_msg", "payload": {"type": "item_completed", "item": {
        "type": "FileChange", "changes": {"/r/a.php": "update", "/r/b.php": {"type": 3}}}}},
    {"timestamp": "2026-10-31T10:00:04Z", "type": "event_msg", "payload": {"type": "item_completed", "item": {
        "type": "CommandExecution", "parsed_cmd": "ls", "command": 5, "exit_code": "0"}}},
    {"timestamp": 99, "type": "event_msg", "payload": {"type": "user_message", "message": ["x"]}},
    {"timestamp": "2026-10-31T10:00:06Z", "type": "event_msg", "payload": {"type": "user_message", "message": "pedido válido"}},
]


def write(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(o) + "\n" for o in lines), encoding="utf-8")
    return path


class RobustezTest(TempDirTestCase):
    def test_linhas_hostis_do_claude_nao_quebram_a_leitura(self):
        for bad in HOSTIS_CLAUDE:
            with self.subTest(bad=bad):
                path = write(self.tmp / "c.jsonl", [GOOD, bad, {**GOOD, "message": {"content": "depois"}}])
                s = read_session("claude", path).session
                self.assertGreaterEqual(s.turns, 2)
                self.assertEqual(s.cwd, "/r")
                self.assertIsInstance(s.last_activity_at, str)
                for value in (s.tokens or {}).values():
                    self.assertIsInstance(value, int)

    def test_linhas_hostis_do_codex_nao_quebram_a_leitura(self):
        path = write(self.tmp / "rollout-2026-10-31T10-00-00-019a0000-0000-7000-8000-000000000001.jsonl", HOSTIS_CODEX)
        s = read_session("codex", path).session
        self.assertEqual(s.id, "019a0000-0000-7000-8000-000000000001")  # id não texto é ignorado
        self.assertEqual(s.turns, 1)
        self.assertEqual(s.first_user_message, "pedido válido")
        self.assertEqual([f.path for f in s.files], ["/r/a.php", "/r/b.php"])
        self.assertTrue(all(isinstance(v, int) for v in (s.tokens or {}).values()))

    def test_excecao_numa_linha_vira_parse_error_e_a_leitura_segue(self):
        path = write(self.tmp / "c.jsonl", [GOOD, GOOD, {**GOOD, "message": {"content": "terceiro"}}])
        original = claude_reader.ClaudeReader._user
        calls = []

        def explode_once(reader, obj, message, at):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError("defeito simulado no leitor")
            return original(reader, obj, message, at)

        with mock.patch.object(claude_reader.ClaudeReader, "_user", explode_once):
            res = read_session("claude", path)
        self.assertEqual(res.session.turns, 2)
        self.assertEqual(res.session.parse_errors, 1)
        self.assertIn("defeito simulado", res.errors[0][1])
        self.assertEqual(res.offset, path.stat().st_size)

    def test_observador_tenta_de_novo_o_arquivo_que_falhou(self):
        env = {"CLAUDE_CONFIG_DIR": str(self.tmp / "claude"), "CODEX_HOME": str(self.tmp / "nada"), "HOME": str(self.tmp)}
        path = write(self.tmp / "claude" / "projects" / "-r" / "aaaa.jsonl", [GOOD] + HOSTIS_CLAUDE)
        index = AgentIndex(self.tmp / "db" / "agentes.db")
        watcher = AgentWatcher(index, env)
        with mock.patch.object(index, "update_file", side_effect=OSError("disco ocupado")):
            self.assertEqual(watcher.run_once(), [])
        self.assertIn("disco ocupado", watcher.last_error)
        self.assertEqual(watcher.run_once(), ["aaaa"])  # o arquivo não ficou marcado como lido
        self.assertEqual(len(index.sessions()), 1)
        index.close()
        self.assertTrue(path.is_file())

    def test_reindexar_agentes_nao_aborta(self):
        write(self.tmp / "claude" / "projects" / "-r" / "aaaa.jsonl", [GOOD] + HOSTIS_CLAUDE)
        env = {"CLAUDE_CONFIG_DIR": str(self.tmp / "claude"), "CODEX_HOME": str(self.tmp / "nada"),
               "HOME": str(self.tmp), "VULCAN_TERMINAL_HOME": str(self.tmp / "home")}
        out = io.StringIO()
        with mock.patch.dict(os.environ, env), redirect_stdout(out):
            self.assertEqual(main(["--reindexar-agentes"]), 0)
        self.assertEqual(json.loads(out.getvalue())["sessions"], 1)

    def test_sidechain_do_assistente_nao_conta(self):
        side = {"type": "assistant", "isSidechain": True, "timestamp": "2026-10-31T10:00:09Z", "message": {
            "id": "s1", "usage": {"input_tokens": 10, "output_tokens": 5}, "content": [
                {"type": "tool_use", "name": "Write", "input": {"file_path": "/r/novo.php"}}]}}
        s = read_session("claude", write(self.tmp / "c.jsonl", [GOOD, side])).session
        self.assertEqual(s.files, [])
        self.assertIsNone(s.tokens)
        self.assertEqual(s.last_activity_at, "2026-10-31T10:00:09Z")  # atividade, mas não conteúdo da sessão

    def test_datas_com_fracao_fora_do_padrao(self):
        for raw, expected in (("2026-10-31T10:00:00.123Z", 123000), ("2026-10-31T10:00:00.123456789Z", 123456),
                              ("2026-10-31T10:00:00.1Z", 100000), ("2026-10-31T10:00:00Z", 0),
                              ("2026-10-31T10:00:00.5+02:00", 500000)):
            with self.subTest(raw=raw):
                self.assertEqual(parse_iso(raw).microsecond, expected)
        for bad in ("", None, "ontem", 12):
            self.assertIsNone(parse_iso(bad))
