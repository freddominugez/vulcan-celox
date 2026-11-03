"""Leitor do Codex com fixture real anonimizada (0.166.0) e fixture sintética de versão anterior."""

import json
import unittest

from tests.helpers import FIXTURES, TempDirTestCase
from vulcan_celox.core.agents import discovery
from vulcan_celox.core.agents.reading import read_session

CODEX = FIXTURES / "agents" / "codex"
SID = "019a0000-1111-7222-8333-444444444444"
REAL = CODEX / "sessions" / "2026" / "10" / "30" / f"rollout-2026-10-30T21-15-44-{SID}.jsonl"
OLD_ID = "019aaaaa-bbbb-7ccc-8ddd-eeeeeeeeeeee"
PATCH = ("*** Begin Patch\n*** Add File: /Users/dev/loja/app/Cupom.php\n+<?php\n*** Update File: /Users/dev/loja/routes/web.php\n"
         "@@\n-a\n+b\n*** Delete File: /Users/dev/loja/velho.php\n*** End Patch\n")


def ev(at, kind, payload):
    return {"timestamp": at, "type": kind, "payload": payload}


class CodexFixtureRealTest(unittest.TestCase):
    """Valores conferidos por um script de contagem independente do leitor."""

    def setUp(self):
        self.s = read_session("codex", REAL).session

    def test_identidade(self):
        s = self.s
        self.assertEqual((s.id, s.agent, s.cwd, s.project_name), (SID, "codex", "/Users/dev/clerk", "clerk"))
        self.assertEqual((s.model, s.cli_version), ("gpt-6.1-sol", "0.166.0"))
        self.assertIsNone(s.git_branch)  # o 0.166.0 não grava git: o app resolve pelo cwd
        self.assertEqual(s.parse_errors, 0)

    def test_pedidos_comandos_e_arquivos_do_item_completed(self):
        s = self.s
        self.assertEqual(s.turns, 3)
        self.assertEqual(s.first_user_message, "pedido 1")
        self.assertEqual(s.commands_total, 23)
        kinds = {f.path.replace("/Users/dev/clerk/", ""): f.kind for f in s.files}
        self.assertEqual(kinds, {"AGENTS.md": "edit", "CLAUDE.md": "edit",
                                 "CONTRATOS/CONSOLIDADO-CONSTRUCAO-CORRECAO-2026-10-30.md": "new"})
        self.assertEqual(s.published, "none")

    def test_tokens_do_ultimo_total(self):
        self.assertEqual(self.s.tokens, {"input": 2094180 - 1964416, "output": 14225, "cache_read": 1964416, "cache_write": 0})


class CodexVersaoAnteriorTest(TempDirTestCase):
    def lines(self):
        return [
            ev("2026-10-20T10:00:00Z", "session_meta", {"id": OLD_ID, "cwd": "/Users/dev/loja", "cli_version": "0.40.0",
                                                         "git": {"branch": "feat/cupom", "commit_hash": "abc"}}),
            ev("2026-10-20T10:00:01Z", "turn_context", {"model": "gpt-5-codex", "cwd": "/Users/dev/loja"}),
            ev("2026-10-20T10:00:02Z", "response_item", {"type": "message", "role": "user",
                                                          "content": [{"type": "input_text", "text": "<environment_context>x"}]}),
            ev("2026-10-20T10:00:03Z", "event_msg", {"type": "user_message", "message": "crie o cupom"}),
            ev("2026-10-20T10:00:03Z", "event_msg", {"type": "item_completed",
                                                     "item": {"type": "UserMessage", "content": [{"type": "text", "text": "crie o cupom"}]}}),
            ev("2026-10-20T10:00:05Z", "response_item", {"type": "function_call", "name": "apply_patch",
                                                          "arguments": json.dumps({"input": PATCH})}),
            ev("2026-10-20T10:00:06Z", "response_item", {"type": "function_call", "name": "shell",
                                                          "arguments": json.dumps({"command": ["bash", "-lc", "php artisan test"]})}),
            ev("2026-10-20T10:00:07Z", "response_item", {"type": "custom_tool_call", "name": "shell",
                                                          "input": json.dumps({"command": "git commit -am cupom"})}),
            ev("2026-10-20T10:30:00Z", "session_meta", {"id": "outro-id-de-sessao-retomada", "cwd": "/outra"}),
            ev("2026-10-20T10:31:00Z", "compacted", {}),
            ev("2026-10-20T10:31:00Z", "tipo_do_futuro", {"x": 1}),
        ]

    def write(self, name, lines):
        path = self.tmp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(o) + "\n" for o in lines), encoding="utf-8")
        return path

    def test_apply_patch_shell_e_meta(self):
        path = self.write(f"sessions/2026/10/20/rollout-2026-10-20T10-00-00-{OLD_ID}.jsonl", self.lines())
        s = read_session("codex", path).session
        self.assertEqual((s.id, s.git_branch, s.model, s.cwd), (OLD_ID, "feat/cupom", "gpt-5-codex", "/Users/dev/loja"))
        kinds = {f.path.rsplit("/", 1)[-1]: f.kind for f in s.files}
        self.assertEqual(kinds, {"Cupom.php": "new", "web.php": "edit", "velho.php": "delete"})
        self.assertEqual([c.kind for c in s.commands], ["test", "publish"])
        self.assertEqual(s.published, "committed")
        self.assertEqual(s.turns, 1)  # user_message e UserMessage iguais contam uma vez
        self.assertEqual(s.first_user_message, "crie o cupom")
        self.assertEqual(s.last_activity_at, "2026-10-20T10:31:00Z")

    def test_reserva_de_pedido_pela_mensagem_de_usuario(self):
        lines = [self.lines()[0], ev("t1", "response_item", {"type": "message", "role": "user",
                                                              "content": [{"type": "input_text", "text": "arrume o README"}]})]
        s = read_session("codex", self.write("r.jsonl", lines)).session
        self.assertEqual((s.turns, s.first_user_message), (1, "arrume o README"))

    def test_origem_da_sessao(self):
        """Subagente e app desktop são marcados; terminal e versão antiga ficam sem marca."""
        def origin(meta):
            path = self.tmp / "rollout-o.jsonl"
            path.write_text(json.dumps({"type": "session_meta", "payload": dict({"id": "o", "cwd": "/r"}, **meta)}) + "\n", encoding="utf-8")
            return read_session("codex", path).session.origin
        self.assertEqual(origin({"originator": "codex-tui", "source": "vscode", "thread_source": "user"}), "")
        self.assertEqual(origin({"originator": "codex-tui", "source": {"subagent": {"thread_spawn": {}}}, "thread_source": "subagent"}), "subagent")
        self.assertEqual(origin({"thread_source": "subagent"}), "subagent")
        self.assertEqual(origin({"originator": "codex_work_desktop", "source": "vscode", "thread_source": "user"}), "desktop")
        self.assertEqual(origin({}), "")

    def test_descoberta_com_arquivadas_e_zst(self):
        self.write(f"a/sessions/2026/10/20/rollout-2026-10-20T10-00-00-{OLD_ID}.jsonl", self.lines())
        self.write("a/archived_sessions/rollout-velho.jsonl", self.lines())
        (self.tmp / "a" / "sessions" / "2026" / "10" / "20" / "rollout-z.jsonl.zst").write_bytes(b"\x28\xb5")
        self.write("b/sessions/2026/10/21/rollout-b.jsonl", self.lines())
        files, zst = discovery.codex_session_files(discovery.codex_roots({"CODEX_HOME": f"{self.tmp / 'a'},{self.tmp / 'b'}"}))
        self.assertEqual(sorted(p.name for p in files), ["rollout-2026-10-20T10-00-00-" + OLD_ID + ".jsonl", "rollout-b.jsonl", "rollout-velho.jsonl"])
        self.assertEqual(zst, 1)


if __name__ == "__main__":
    unittest.main()
