"""Registro das edições. Fixtures sintéticas: nada aqui veio de sessão real."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from vulcan_celox.core.agents import edits
from vulcan_celox.core.agents.index import AgentIndex

SID = "77777777-8888-4999-8aaa-bbbbbbbbbbbb"


def tool_use(tool_id, name, **data):
    return {"type": "assistant", "timestamp": "2026-11-02T10:00:01Z", "cwd": "/sintetico/projeto",
            "message": {"role": "assistant", "content": [{"type": "tool_use", "id": tool_id, "name": name, "input": data}]}}


def tool_result(tool_id, error=False, result=None):
    line = {"type": "user", "timestamp": "2026-11-02T10:00:02Z", "cwd": "/sintetico/projeto",
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_id, "is_error": error, "content": "x"}]}}
    if result is not None:
        line["toolUseResult"] = result
    return line


PEDIDO = {"type": "user", "timestamp": "2026-11-02T10:00:00Z", "cwd": "/sintetico/projeto",
          "message": {"role": "user", "content": "faça a mudança"}}


class EditsCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.index = AgentIndex(self.tmp / "agentes.db")
        self.addCleanup(self.index.close)
        self.file = self.tmp / f"{SID}.jsonl"

    def append(self, *lines, path=None):
        with open(path or self.file, "a", encoding="utf-8") as fh:
            for line in lines:
                fh.write((line if isinstance(line, str) else json.dumps(line)) + "\n")

    def read(self, agent="claude", path=None, sid=SID):
        self.index.update_file(agent, path or self.file)
        return edits.rows_of(self.index, sid)

    def detail(self, row, agent="claude", path=None):
        return edits.edit_detail(agent, str(path or self.file), row)


class ClaudeEditsTest(EditsCase):
    def test_edicao_com_structured_patch(self):
        hunk = {"oldStart": 1, "oldLines": 2, "newStart": 1, "newLines": 2, "lines": [" igual", "-antes", "+depois"]}
        self.append(PEDIDO, tool_use("t1", "Edit", file_path="/sintetico/projeto/a.py", old_string="antes", new_string="depois"),
                    tool_result("t1", result={"structuredPatch": [hunk], "originalFile": "igual\nantes\n"}))
        row = self.read()[0]
        self.assertEqual((row["seq"], row["path"], row["tool"], row["turn"], row["state"], row["kind"]),
                         (1, "/sintetico/projeto/a.py", "Edit", 1, "ok", "edit"))
        self.assertEqual(self.detail(row), {"available": True, "old": "igual\nantes", "new": "igual\ndepois",
                                            "complete": False, "replace_all": False})

    def test_edicao_falha(self):
        self.append(PEDIDO, tool_use("t1", "Edit", file_path="/p/a.py", old_string="x", new_string="y"), tool_result("t1", error=True))
        row = self.read()[0]
        self.assertEqual(row["state"], "failed")
        self.assertEqual(self.detail(row)["new"], "y")

    def test_replace_all_sem_resultado(self):
        self.append(PEDIDO, tool_use("t1", "Edit", file_path="/p/a.py", old_string="x", new_string="y", replace_all=True))
        row = self.read()[0]
        self.assertEqual(row["state"], "pending")
        got = self.detail(row)
        self.assertTrue(got["replace_all"])
        self.assertEqual((got["old"], got["new"]), ("x", "y"))

    def test_multiedit(self):
        self.append(PEDIDO, tool_use("t1", "MultiEdit", file_path="/p/a.py", edits=[{"old_string": "a", "new_string": "b"}, {"old_string": "c", "new_string": "d"}]))
        got = self.detail(self.read()[0])
        self.assertEqual((got["old"], got["new"]), ("a\n…\nc", "b\n…\nd"))

    def test_write_novo_e_sobre_existente(self):
        self.append(PEDIDO, tool_use("t1", "Write", file_path="/p/novo.py", content="um"),
                    tool_result("t1", result={"type": "create", "content": "um", "originalFile": None}),
                    tool_use("t2", "Write", file_path="/p/velho.py", content="dois"),
                    tool_result("t2", result={"type": "update", "originalFile": "antigo", "structuredPatch": []}))
        novo, velho = self.read()
        self.assertEqual((novo["kind"], velho["kind"]), ("create", "edit"))
        self.assertEqual(self.detail(novo), {"available": True, "old": "", "new": "um", "complete": True})
        self.assertEqual(self.detail(velho), {"available": True, "old": "antigo", "new": "dois", "complete": True})

    def test_write_sem_resultado_nao_finge_arquivo_todo(self):
        self.append(PEDIDO, tool_use("t1", "Write", file_path="/p/a.py", content="um"))
        self.assertFalse(self.detail(self.read()[0])["complete"])

    def test_conteudo_nao_vai_para_o_indice(self):
        self.append(PEDIDO, tool_use("t1", "Write", file_path="/p/a.py", content="CONTEUDO-SECRETO"),
                    tool_result("t1", result={"type": "update", "originalFile": "ORIGINAL-SECRETO"}))
        self.read()
        self.index.close()
        banco = b"".join(p.read_bytes() for p in self.tmp.glob("agentes.db*"))
        self.index = AgentIndex(self.tmp / "agentes.db")
        self.assertNotIn(b"ORIGINAL-SECRETO", banco)
        self.assertNotIn(b"CONTEUDO-SECRETO", banco)

    def test_incremental_nao_duplica_e_resultado_chega_depois(self):
        self.append(PEDIDO, tool_use("t1", "Edit", file_path="/p/a.py", old_string="x", new_string="y"))
        self.assertEqual([r["state"] for r in self.read()], ["pending"])
        self.append(tool_result("t1"))
        self.assertEqual([r["state"] for r in self.read()], ["ok"])
        self.append(tool_use("t2", "Edit", file_path="/p/b.py", old_string="x", new_string="y"))
        got = self.read()
        self.assertEqual([(r["seq"], r["path"]) for r in got], [(1, "/p/a.py"), (2, "/p/b.py")])
        self.assertEqual(self.detail(got[1])["new"], "y")

    def test_subagente_e_leitura_nao_entram(self):
        sub = tool_use("t1", "Edit", file_path="/p/a.py", old_string="x", new_string="y")
        sub["isSidechain"] = True
        self.append(PEDIDO, sub, tool_use("t2", "Read", file_path="/p/b.py"))
        self.assertEqual(self.read(), [])

    def test_linha_gigante_fica_sem_diff(self):
        big = tool_use("t1", "Write", file_path="/p/gigante.py", content="x" * (5 * 1024 * 1024 + 10))
        self.append(PEDIDO, big, tool_use("t2", "Edit", file_path="/p/b.py", old_string="x", new_string="y"))
        gigante, depois = self.read()
        self.assertEqual((gigante["path"], gigante["state"]), ("/p/gigante.py", "no_diff"))
        self.assertEqual(self.detail(gigante), {"available": False, "reason": "no_diff"})
        self.assertEqual(self.detail(depois)["new"], "y")

    def test_jsonl_apagado_fica_sem_conteudo(self):
        self.append(PEDIDO, tool_use("t1", "Edit", file_path="/p/a.py", old_string="x", new_string="y"))
        row = self.read()[0]
        self.file.unlink()
        self.assertEqual(self.detail(row), {"available": False, "reason": "source_gone"})

    def test_arquivo_encolheu_recomeca_sem_duplicar(self):
        self.append(PEDIDO, tool_use("t1", "Edit", file_path="/p/a.py", old_string="x", new_string="y"),
                    tool_use("t2", "Edit", file_path="/p/b.py", old_string="x", new_string="y"))
        self.assertEqual(len(self.read()), 2)
        self.file.write_text("", encoding="utf-8")
        self.append(PEDIDO)
        self.assertEqual(self.read(), [])


def codex_meta():
    return {"type": "session_meta", "timestamp": "2026-11-02T10:00:00Z",
            "payload": {"id": SID, "cwd": "/sintetico/projeto", "cli_version": "0.0.0-sintetico"}}


def codex_user():
    return {"type": "event_msg", "timestamp": "2026-11-02T10:00:00Z", "payload": {"type": "user_message", "message": "faça"}}


PATCH = "\n".join(["*** Begin Patch", "*** Update File: a.py", "@@", " igual", "-antes", "+depois",
                   "*** Add File: b.py", "+novo", "*** Delete File: c.py", "*** End Patch"])


def codex_call(name, data, kind="custom_tool_call"):
    return {"type": "response_item", "timestamp": "2026-11-02T10:00:01Z",
            "payload": {"type": kind, "name": name, ("input" if kind == "custom_tool_call" else "arguments"): data}}


def file_change(changes, status="completed"):
    return {"type": "event_msg", "timestamp": "2026-11-02T10:00:02Z",
            "payload": {"type": "item_completed", "item": {"type": "FileChange", "status": status, "changes": changes}}}


class CodexEditsTest(EditsCase):
    def setUp(self):
        super().setUp()
        self.file = self.tmp / f"rollout-2026-11-02T10-00-00-{SID}.jsonl"
        self.append(codex_meta(), codex_user())

    def read_codex(self):
        return self.read("codex")

    def test_patch_com_tres_arquivos(self):
        self.append(codex_call("apply_patch", PATCH))
        a, b, c = self.read_codex()
        self.assertEqual([(r["path"], r["kind"], r["turn"]) for r in (a, b, c)],
                         [("a.py", "edit", 1), ("b.py", "create", 1), ("c.py", "delete", 1)])
        self.assertEqual(self.detail(a, "codex"), {"available": True, "old": "igual\nantes", "new": "igual\ndepois", "complete": False})
        self.assertEqual(self.detail(b, "codex"), {"available": True, "old": "", "new": "novo", "complete": True})

    def test_patch_em_heredoc_dentro_de_json(self):
        script = "apply_patch <<'EOF'\n" + PATCH + "\nEOF\n"
        self.append(codex_call("shell", json.dumps({"command": ["bash", "-lc", script]}), "function_call"))
        rows = self.read_codex()
        self.assertEqual([r["path"] for r in rows], ["a.py", "b.py", "c.py"])
        self.assertEqual(self.detail(rows[0], "codex")["new"], "igual\ndepois")

    def test_comando_sem_patch_nao_conta(self):
        self.append(codex_call("exec", "tools.exec_command({cmd: 'ls'})"))
        self.assertEqual(self.read_codex(), [])

    def test_file_change_e_a_mesma_edicao_do_patch_anterior(self):
        diff = "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n igual\n-antes\n+depois\n"
        self.append(codex_call("exec", "tools.apply_patch(`" + PATCH + "`)"),
                    file_change({"a.py": {"type": "update", "unified_diff": diff, "move_path": None},
                                 "b.py": {"type": "add", "content": "novo\n"}, "c.py": {"type": "delete", "content": "velho\n"}}))
        a, b, c = self.read_codex()
        self.assertEqual([(r["seq"], r["tool"]) for r in (a, b, c)], [(1, "FileChange"), (2, "FileChange"), (3, "FileChange")])
        self.assertEqual(self.detail(a, "codex"), {"available": True, "old": "igual\nantes", "new": "igual\ndepois", "complete": False})
        self.assertEqual(self.detail(b, "codex"), {"available": True, "old": "", "new": "novo\n", "complete": True})
        self.assertEqual(self.detail(c, "codex"), {"available": True, "old": "velho\n", "new": "", "complete": True})

    def test_file_change_com_falha(self):
        self.append(file_change({"a.py": {"type": "update", "unified_diff": ""}}, status="failed"))
        self.assertEqual(self.read_codex()[0]["state"], "failed")

    def test_depois_do_file_change_nao_le_patch(self):
        self.append(file_change({"a.py": {"type": "update", "unified_diff": ""}}), codex_call("exec", "tools.apply_patch(`" + PATCH + "`)"))
        self.assertEqual([r["path"] for r in self.read_codex()], ["a.py"])

    def test_linha_gigante_do_patch_fica_sem_diff(self):
        patch = PATCH.replace("+novo", "+" + "x" * (5 * 1024 * 1024))
        self.append(codex_call("apply_patch", patch))
        rows = self.read_codex()
        self.assertEqual([(r["path"], r["state"]) for r in rows], [("a.py", "no_diff"), ("b.py", "no_diff")])

    @unittest.skipUnless(shutil.which("zstd"), "sem zstd")
    def test_jsonl_zst(self):
        self.append(codex_call("apply_patch", PATCH))
        subprocess.run(["zstd", "-q", str(self.file)], check=True)
        packed = Path(str(self.file) + ".zst")
        self.file.unlink()
        a, b, c = self.read("codex", packed)
        self.assertEqual(self.detail(a, "codex", packed)["new"], "igual\ndepois")
        self.assertEqual(self.detail(c, "codex", packed)["new"], "")
        self.assertEqual(self.read("codex", packed), [a, b, c])


if __name__ == "__main__":
    unittest.main()
