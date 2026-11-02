"""vt-16b C3: trilha de publicação e alerta de loop seguem a ordem real e ignoram comandos que falharam."""

import json

from tests.helpers import TempDirTestCase
from vulcan_terminal.core.agents import rules
from vulcan_terminal.core.agents.reading import read_session

CID = "019a0000-0000-7000-8000-00000000c3c3"


def claude_tool(n, name, data, at, tool_id=None):
    return {"type": "assistant", "timestamp": at, "message": {"id": f"m{n}", "usage": {}, "content": [
        {"type": "tool_use", "id": tool_id or f"t{n}", "name": name, "input": data}]}}


def claude_result(tool_id, at, error=False):
    return {"type": "user", "timestamp": at, "message": {"content": [
        {"type": "tool_result", "tool_use_id": tool_id, "is_error": error, "content": "saída"}]}}


def edit(n):
    return claude_tool(n, "Edit", {"file_path": "/r/a.php"}, f"2026-10-31T10:0{n}:00Z")


def bash(n, cmd, error=None):
    lines = [claude_tool(n, "Bash", {"command": cmd}, f"2026-10-31T10:0{n}:00Z")]
    if error is not None:
        lines.append(claude_result(f"t{n}", f"2026-10-31T10:0{n}:30Z", error))
    return lines


def codex_cmd(at, cmd, code):
    return {"timestamp": at, "type": "event_msg", "payload": {"type": "item_completed", "item": {
        "type": "CommandExecution", "parsed_cmd": [{"cmd": cmd}], "exit_code": code}}}


def codex_file(at):
    return {"timestamp": at, "type": "event_msg", "payload": {"type": "item_completed", "item": {
        "type": "FileChange", "changes": {"/r/a.php": {"type": "update"}}}}}


class PublicacaoClaudeTest(TempDirTestCase):
    def read(self, lines):
        path = self.tmp / "s.jsonl"
        path.write_text("".join(json.dumps(o) + "\n" for o in lines), encoding="utf-8")
        return read_session("claude", path).session

    def test_matriz(self):
        casos = [
            ("editou e só fez push", [edit(1), *bash(2, "git push", False)], "none", False),
            ("editou, commit e push", [edit(1), *bash(2, "git commit -am x", False), *bash(3, "git push", False)], "pushed", False),
            ("commit e push no mesmo comando", [edit(1), *bash(2, "git add -A && git commit -m x && git push", False)], "pushed", False),
            ("PR sem push", [edit(1), *bash(2, "git commit -m x", False), *bash(3, "gh pr create --fill", False)], "committed", False),
            ("PR depois do push", [edit(1), *bash(2, "git commit -m x && git push", False), *bash(3, "gh pr create", False)], "pr_open", True),
            ("commit que falhou", [edit(1), *bash(2, "git commit -m x", True)], "none", False),
            ("push rejeitado", [edit(1), *bash(2, "git commit -m x", False), *bash(3, "git push", True)], "committed", False),
            ("resultado ainda não chegou", [edit(1), *bash(2, "git commit -m x")], "none", False),
        ]
        for nome, lines, esperado, pr in casos:
            with self.subTest(nome):
                s = self.read(lines)
                self.assertEqual((s.published, s.pr_opened), (esperado, pr))

    def test_commit_que_falhou_marca_saida_e_nao_zera_o_loop(self):
        tests = [l for i in range(3) for l in bash(i + 1, "pytest -x", True)]
        s = self.read([edit(0), *tests[:4], *bash(5, "git commit -m x", True), *tests[4:]])
        self.assertEqual(s.loop_alert["count"], 3)
        failed = [c for c in s.commands if c.text == "git commit -m x"]
        self.assertEqual(failed[0].exit_code, 1)
        ok = self.read([edit(0), *tests[:4], *bash(5, "git commit -m x", False), *tests[4:]])
        self.assertIsNone(ok.loop_alert)


class PublicacaoCodexTest(TempDirTestCase):
    def read(self, lines):
        path = self.tmp / f"rollout-2026-10-31T10-00-00-{CID}.jsonl"
        head = {"timestamp": "2026-10-31T10:00:00Z", "type": "session_meta", "payload": {"id": CID, "cwd": "/r"}}
        path.write_text("".join(json.dumps(o) + "\n" for o in [head, *lines]), encoding="utf-8")
        return read_session("codex", path).session

    def test_exit_code(self):
        s = self.read([codex_file("2026-10-31T10:01:00Z"), codex_cmd("2026-10-31T10:02:00Z", "git commit -am x", 1),
                       codex_cmd("2026-10-31T10:03:00Z", "git push", 128)])
        self.assertEqual(s.published, "none")
        s = self.read([codex_file("2026-10-31T10:01:00Z"), codex_cmd("2026-10-31T10:02:00Z", "git commit -am x", 0),
                       codex_cmd("2026-10-31T10:03:00Z", "git push", 0)])
        self.assertEqual(s.published, "pushed")

    def test_pedidos_iguais_em_turnos_diferentes_contam_os_dois(self):
        def user(at, kind="user_message"):
            if kind == "user_message":
                return {"timestamp": at, "type": "event_msg", "payload": {"type": "user_message", "message": "continue"}}
            return {"timestamp": at, "type": "event_msg", "payload": {"type": "item_completed", "item": {
                "type": "UserMessage", "content": [{"type": "text", "text": "continue"}]}}}
        s = self.read([user("2026-10-31T10:00:01Z"), user("2026-10-31T10:00:02Z", "item"),  # o mesmo pedido, duas fontes
                       user("2026-10-31T10:05:00Z"), user("2026-10-31T10:05:01Z", "item")])  # o mesmo texto, outro turno
        self.assertEqual(s.turns, 2)


class RegrasTest(TempDirTestCase):
    def test_sequencia_de_publicacao_por_trecho(self):
        self.assertEqual(rules.publish_sequence("git add -A && git commit -m x && git push && gh pr create"),
                         ["committed", "pushed", "pr_open"])
        self.assertEqual(rules.publish_sequence("git status; ls"), [])
