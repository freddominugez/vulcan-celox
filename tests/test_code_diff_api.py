"""Tree, edits and diff of the viewer. Synthetic fixtures; a hostile repository cannot run anything."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import quote

from tests.test_agents_api import AgentsServerCase

ROOT = Path(__file__).resolve().parent.parent
SID = "88888888-5555-4666-8777-888888888888"


def git(folder, *args):
    subprocess.run(["git", "-C", str(folder), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                   check=True, capture_output=True)


class CodeDiffCase(AgentsServerCase):
    def setUp(self):
        super().setUp()
        self.project = (self.tmp / "projeto").resolve()
        self.project.mkdir()
        (self.project / "a.py").write_text("um\nmudou\n", encoding="utf-8")
        self.jsonl = self.tmp / "claude" / "projects" / "-tmp-projeto" / f"{SID}.jsonl"
        self.jsonl.parent.mkdir(parents=True, exist_ok=True)
        self.lines = [self.user("primeiro")]
        self.save()

    def user(self, text):
        return {"type": "user", "timestamp": "2026-11-02T10:00:00Z", "cwd": str(self.project),
                "message": {"role": "user", "content": text}}

    def edit(self, tool_id, path, old, new):
        return {"type": "assistant", "timestamp": "2026-11-02T10:00:01Z", "cwd": str(self.project),
                "message": {"role": "assistant", "content": [{"type": "tool_use", "id": tool_id, "name": "Edit",
                            "input": {"file_path": str(path), "old_string": old, "new_string": new}}]}}

    def save(self):
        self.jsonl.write_text("".join(json.dumps(x) + "\n" for x in self.lines), encoding="utf-8")
        self.app.agents.refresh()

    def diff(self, path, scope, seq=None):
        url = f"/api/code/session/{SID}/diff?path={quote(str(path))}&scope={scope}"
        return self.request("GET", url + (f"&seq={seq}" if seq else ""))[:2]


class TreeAndEditsTest(CodeDiffCase):
    def test_arvore_marca_editado_sensivel_e_fora(self):
        self.lines += [self.edit("t1", self.project / "a.py", "x", "y"), self.edit("t2", self.project / ".env", "x", "y"),
                       self.edit("t3", "/fora/z.py", "x", "y"),
                       {"type": "assistant", "timestamp": "2026-11-02T10:00:01Z", "message": {"role": "assistant", "content": [
                           {"type": "tool_use", "id": "t4", "name": "Read", "input": {"file_path": str(self.project / "b.py")}}]}}]
        self.save()
        data = self.get(f"/api/code/session/{SID}/tree")
        files = {f["rel"]: f for f in data["files"]}
        self.assertEqual(data["root"], str(self.project))
        self.assertEqual((files["a.py"]["kind"], files["a.py"]["edits"], files["a.py"]["inside"], files["a.py"]["exists"]), ("edit", 1, True, True))
        self.assertTrue(files[".env"]["sensitive"])
        self.assertFalse(next(f for rel, f in files.items() if Path(rel).name == "z.py")["inside"])
        self.assertEqual(files["b.py"]["kind"], "read")
        self.assertEqual(data["total_edits"], 3)

    def test_edits_paginado(self):
        self.lines += [self.edit(f"t{i}", self.project / "a.py", "x", str(i)) for i in range(5)]
        self.save()
        first = self.get(f"/api/code/session/{SID}/edits?limit=2")
        self.assertEqual([r["seq"] for r in first["edits"]], [1, 2])
        second = self.get(f"/api/code/session/{SID}/edits?limit=2&start={first['next']}")
        self.assertEqual([r["seq"] for r in second["edits"]], [3, 4])
        self.assertEqual(self.request("GET", f"/api/code/session/{SID}/edits?limit=abc")[0], 400)

    def test_nao_existe_escrita(self):
        for path in ("tree", "edits", "diff"):
            self.assertIn(self.request("POST", f"/api/code/session/{SID}/{path}", {})[0], (404, 405))

    def test_exige_token(self):
        self.assertEqual(self.request("GET", f"/api/code/session/{SID}/tree", token=False)[0], 401)


class EditAndTurnScopeTest(CodeDiffCase):
    def test_por_edicao_e_por_turno(self):
        self.lines += [self.edit("t1", self.project / "a.py", "a1", "b1"), self.edit("t2", self.project / "a.py", "a2", "b2"),
                       self.user("segundo"), self.edit("t3", self.project / "a.py", "a3", "b3")]
        self.save()
        status, data = self.diff(self.project / "a.py", "edit", 2)
        self.assertEqual((status, data["old"], data["new"], data["turn"]), (200, "a2", "b2", 1))
        status, data = self.diff(self.project / "a.py", "turn", 1)
        self.assertEqual((status, data["old"], data["new"], data["edits"]), (200, "a1\n…\na2", "b1\n…\nb2", [1, 2]))
        self.assertFalse(data["complete"])
        status, data = self.diff("a.py", "edit")
        self.assertEqual((status, data["new"]), (200, "b3"))

    def test_seq_de_outro_arquivo_nao_serve(self):
        self.lines += [self.edit("t1", self.project / "a.py", "x", "y"), self.edit("t2", self.project / "b.py", "SEGREDO", "y")]
        self.save()
        status, data = self.diff(self.project / "a.py", "edit", 2)
        self.assertEqual((status, data["reason"]), (404, "no_edit"))

    def test_escopos_recusam_fora_da_raiz_e_sensivel(self):
        self.lines += [self.edit("t1", self.project / ".env", "SEGREDO", "y"), self.edit("t2", "/fora/z.py", "SEGREDO", "y")]
        self.save()
        for scope in ("edit", "turn", "git"):
            with self.subTest(escopo=scope):
                status, data = self.diff(self.project / ".env", scope)
                self.assertEqual((status, data["reason"]), (403, "sensitive"))
                status, data = self.diff("/fora/z.py", scope)
                self.assertEqual((status, data["reason"]), (403, "outside"))
                status, data = self.diff("../fora.py", scope)
                self.assertEqual((status, data["reason"]), (403, "outside"))

    def test_escopo_invalido(self):
        self.assertEqual(self.diff("a.py", "tudo")[0], 400)

    def test_edicao_grande_e_cortada_com_aviso(self):
        self.lines += [self.edit("t1", self.project / "a.py", "x", "y" * (2 * 1024 * 1024 + 5))]
        self.save()
        status, data = self.diff("a.py", "edit", 1)
        self.assertEqual((status, data["truncated"], data["complete"]), (200, True, False))
        self.assertEqual(len(data["new"]), 2 * 1024 * 1024)


class SemGitTest(CodeDiffCase):
    def test_sem_o_comando_git_diz_o_motivo(self):
        with mock.patch("vulcan_celox.core.code_diff.capture", return_value=(None, b"", False)):
            status, data = self.diff("a.py", "git")
        self.assertEqual((status, data["available"], data["reason"]), (200, False, "no_git"))


@unittest.skipUnless(shutil.which("git"), "sem git")
class GitScopeTest(CodeDiffCase):
    def repo(self):
        git(self.project, "init", "-q")
        git(self.project, "add", "a.py")
        (self.project / "a.py").write_text("um\ndois\n", encoding="utf-8")
        git(self.project, "add", "a.py")
        git(self.project, "commit", "-qm", "base")
        (self.project / "a.py").write_text("um\nmudou\n", encoding="utf-8")

    def test_modificado_novo_e_apagado(self):
        self.repo()
        status, data = self.diff("a.py", "git")
        self.assertEqual((status, data["status"], data["old"], data["new"]), (200, "modified", "um\ndois\n", "um\nmudou\n"))
        (self.project / "novo.py").write_bytes(b"n\n")
        status, data = self.diff("novo.py", "git")
        self.assertEqual((data["status"], data["old"], data["new"]), ("new", "", "n\n"))
        (self.project / "a.py").unlink()
        status, data = self.diff("a.py", "git")
        self.assertEqual((data["status"], data["old"], data["new"]), ("deleted", "um\ndois\n", ""))
        self.assertEqual(self.diff("nunca.py", "git")[1]["reason"], "missing")

    def test_sem_repositorio(self):
        status, data = self.diff("a.py", "git")
        self.assertEqual((status, data["available"], data["reason"]), (200, False, "no_repo"))

    def test_corte_em_2_mb(self):
        self.repo()
        (self.project / "g.txt").write_bytes(b"x" * (3 * 1024 * 1024))
        git(self.project, "add", "g.txt")
        git(self.project, "commit", "-qm", "grande")
        (self.project / "g.txt").write_text("pouco", encoding="utf-8")
        status, data = self.diff("g.txt", "git")
        self.assertEqual((status, data["truncated"], data["complete"], len(data["old"])), (200, True, False, 2 * 1024 * 1024))

    def test_repositorio_hostil_nao_executa_nada(self):
        self.repo()
        marca = self.tmp / "executou"
        script = self.tmp / "hostil.sh"
        script.write_text(f"#!/bin/sh\ntouch '{marca}'\ncat\n", encoding="utf-8")
        script.chmod(0o755)
        (self.project / ".gitattributes").write_text("* diff=h filter=h\n", encoding="utf-8")
        for key, value in (("diff.external", script), ("diff.h.textconv", script), ("diff.h.command", script),
                           ("filter.h.clean", script), ("filter.h.smudge", script), ("core.fsmonitor", script),
                           ("core.pager", script)):
            git(self.project, "config", key, str(value))
        status, data = self.diff("a.py", "git")
        self.assertEqual((status, data["status"]), (200, "modified"))
        self.get(f"/api/code/session/{SID}/tree")
        self.assertFalse(marca.exists(), "o repositório conseguiu executar um programa")
        self.assertEqual(data["old"], "um\ndois\n")


class EntradaEDocumentosTest(unittest.TestCase):
    def test_botao_do_terminal_so_na_aba_pareada(self):
        bar = (ROOT / "vulcan_celox" / "web" / "js" / "prompt-bar.mjs").read_text(encoding="utf-8")
        self.assertIn("s.pairing_id === this.terminal", bar)
        self.assertRegex(bar, r'paired \? `<a class="pb-chip pb-code" href="#/agentes/\$\{encodeURIComponent\(s\.id\)\}/codigo"')

    def test_rotas_na_documentacao(self):
        doc = (ROOT / "docs" / "en" / "http-api.md").read_text(encoding="utf-8")
        for route in ("/api/code/file", "/api/code/session/<sid>/tree", "/api/code/session/<sid>/edits", "/api/code/session/<sid>/diff"):
            self.assertIn(route, doc)

    def test_visor_nao_virou_editor_no_roadmap(self):
        self.assertIn("does not edit files", (ROOT / "ROADMAP.md").read_text(encoding="utf-8"))
        self.assertIn("não edita arquivos", (ROOT / "ROADMAP.pt-BR.md").read_text(encoding="utf-8"))
