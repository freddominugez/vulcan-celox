"""vt-16 C3: leitor do Claude Code com fixture real anonimizada e casos sintéticos."""

import json
import tempfile
import unittest
from pathlib import Path

from tests.helpers import FIXTURES, TempDirTestCase
from vulcan_terminal.core.agents import discovery, rules
from vulcan_terminal.core.agents.reading import read_session

CLAUDE = FIXTURES / "agents" / "claude"
SID = "11111111-2222-4333-8444-555555555555"
REAL = CLAUDE / "projects" / "-Users-dev-projeto" / f"{SID}.jsonl"


def user(text, at, **extra):
    return {"type": "user", "timestamp": at, "cwd": "/Users/dev/loja", "gitBranch": "feat/x", "sessionId": "s",
            "message": {"role": "user", "content": text}, **extra}


def tool(mid, name, data, at, usage=None):
    return {"type": "assistant", "timestamp": at, "cwd": "/Users/dev/loja", "gitBranch": "feat/x",
            "message": {"id": mid, "model": "claude-opus-5-5", "content": [{"type": "tool_use", "name": name, "input": data}],
                        "usage": usage or {"input_tokens": 1, "output_tokens": 10}}}


class ClaudeFixtureRealTest(unittest.TestCase):
    """Valores conferidos por um script de contagem independente do leitor."""

    def setUp(self):
        self.r = read_session("claude", REAL)
        self.s = self.r.session

    def test_identidade(self):
        s = self.s
        self.assertEqual((s.id, s.agent, s.cwd, s.project_name, s.git_branch), (SID, "claude", "/Users/dev/projeto", "projeto", "main"))
        self.assertEqual(s.model, "claude-opus-5-5")
        self.assertEqual(s.title, "Título de exemplo")
        self.assertTrue(s.started_at < s.last_activity_at)
        self.assertEqual(s.parse_errors, 0)

    def test_tokens_deduplicados_por_message_id(self):
        self.assertEqual(self.s.tokens, {"input": 130, "output": 195809, "cache_read": 15626815, "cache_write": 351903})

    def test_arquivos_e_comandos(self):
        kinds = {f.path.replace("/Users/dev/projeto/", ""): f.kind for f in self.s.files}
        self.assertEqual(len(kinds), 13)
        self.assertEqual(kinds["CLAUDE.md"], "edit")             # lido e depois reescrito
        self.assertEqual(kinds["docs/PLANO-CONSTRUTIVO-AGENTES.md"], "new")  # criado e depois editado
        self.assertEqual(kinds["PROMPT-EXECUCAO.md"], "edit")
        self.assertEqual(kinds["fora/byyui9qc3.txt"], "read")
        self.assertNotIn("nao-contar.py", " ".join(kinds))      # api-request-blob é ignorado
        self.assertEqual(self.s.commands_total, 41)
        self.assertEqual({c.kind for c in self.s.commands}, {"shell"})
        self.assertEqual(self.s.published, "none")

    def test_pedidos(self):
        self.assertGreaterEqual(self.s.turns, 7)
        self.assertEqual(self.s.first_user_message, "pedido 1")
        kinds = {e.kind for e in self.r.events}
        self.assertEqual(kinds, {"user", "assistant", "file", "command"})

    def test_leitura_em_partes_igual_a_inteira(self):
        data = REAL.read_bytes()
        for cut in (len(data) // 3, len(data) // 2 + 7):  # o segundo corte cai no meio de uma linha
            with self.subTest(cut=cut):
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / f"{SID}.jsonl"
                    path.write_bytes(data[:cut])
                    first = read_session("claude", path)
                    path.write_bytes(data)
                    second = read_session("claude", path, first.session, first.state, first.offset)
                    whole = self.s.to_dict()
                    got = second.session.to_dict()
                    for d in (whole, got):
                        d.pop("file_path")
                    self.assertEqual(got, whole)
                    self.assertEqual(len(first.events) + len(second.events), len(self.r.events))


class ClaudeSinteticoTest(TempDirTestCase):
    def read(self, lines):
        path = self.tmp / "s.jsonl"
        path.write_text("".join(json.dumps(o) + "\n" for o in lines), encoding="utf-8")
        return read_session("claude", path).session

    def test_publicacao_e_edicao_depois_do_commit(self):
        base = [user("corrija o frete", "2026-10-30T10:00:00Z"),
                tool("m1", "Edit", {"file_path": "/Users/dev/loja/a.php"}, "2026-10-30T10:01:00Z")]
        commit = [tool("m2", "Bash", {"command": "git add -A && git commit -m x"}, "2026-10-30T10:02:00Z")]
        push = [tool("m3", "Bash", {"command": "git push -u origin feat/x"}, "2026-10-30T10:03:00Z")]
        pr = [tool("m4", "Bash", {"command": "gh pr create --fill"}, "2026-10-30T10:04:00Z")]
        edit_again = [tool("m5", "Write", {"file_path": "/Users/dev/loja/b.php"}, "2026-10-30T10:05:00Z")]
        self.assertEqual(self.read(base).published, "none")
        self.assertEqual(self.read(base + commit).published, "committed")
        self.assertEqual(self.read(base + commit + push).published, "pushed")
        self.assertEqual(self.read(base + commit + push + pr).published, "pr_open")
        s = self.read(base + commit + push + pr + edit_again)
        self.assertEqual(s.published, "none")
        self.assertTrue(s.pr_opened)
        self.assertEqual([c.kind for c in s.commands], ["publish", "publish", "publish"])

    def test_tokens_de_linhas_repetidas_contam_uma_vez(self):
        u = {"input_tokens": 5, "output_tokens": 50, "cache_read_input_tokens": 100}
        s = self.read([tool("m1", "Read", {"file_path": "/a"}, "t1", u), tool("m1", "Bash", {"command": "ls"}, "t2", u),
                       tool("m2", "Read", {"file_path": "/b"}, "t3", u)])
        self.assertEqual(s.tokens, {"input": 10, "output": 100, "cache_read": 200, "cache_write": 0})

    def test_ignora_meta_sidechain_e_comandos_do_cli(self):
        s = self.read([user("<command-name>/model</command-name>", "t1"), user("x", "t2", isMeta=True),
                       user("y", "t3", isSidechain=True), user("pedido de verdade", "t4"),
                       {"type": "api-request-blob", "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": "/z"}}]}},
                       {"type": "tipo-novo-qualquer", "x": 1}])
        self.assertEqual(s.turns, 1)
        self.assertEqual(s.first_user_message, "pedido de verdade")
        self.assertEqual(s.files, [])

    def test_teste_e_chave_do_teste(self):
        s = self.read([tool("m1", "Bash", {"command": "cd /Users/dev/loja && php artisan test --filter=Frete 2>&1 | tail -5"}, "t1")])
        self.assertEqual(s.commands[0].kind, "test")
        self.assertEqual(rules.test_key(s.commands[0].text), "php artisan test --filter=Frete 2>&1")

    def test_worktree_do_claude(self):
        line = user("oi", "t1")
        line["cwd"] = "/Users/dev/loja/.claude/worktrees/cupom"
        s = self.read([line])
        self.assertEqual((s.project_name, s.project_root, s.worktree), ("loja", "/Users/dev/loja", "cupom"))


class ClaudeDiscoveryTest(TempDirTestCase):
    def test_sessoes_e_subagentes(self):
        proj = self.tmp / "projects" / "-Users-dev-loja"
        (proj / "s1" / "subagents").mkdir(parents=True)
        (proj / "s1.jsonl").write_text("{}\n")
        (proj / "s1" / "subagents" / "agent-a.jsonl").write_text("{}\n")
        (proj / "agent-b.jsonl").write_text(json.dumps({"sessionId": "s1"}) + "\n")
        self.assertEqual([p.name for p in discovery.claude_session_files(self.tmp)], ["s1.jsonl"])
        self.assertEqual(discovery.claude_subagent_counts(self.tmp), {"s1": 2})

    def test_raiz_por_variavel_e_por_home(self):
        self.assertEqual(discovery.claude_root({"CLAUDE_CONFIG_DIR": "/x/y"}).as_posix(), "/x/y")
        self.assertEqual(discovery.claude_root({"HOME": "/h"}).as_posix(), "/h/.claude")
        self.assertEqual([p.as_posix() for p in discovery.codex_roots({"CODEX_HOME": "/a, /b"})], ["/a", "/b"])


if __name__ == "__main__":
    unittest.main()
