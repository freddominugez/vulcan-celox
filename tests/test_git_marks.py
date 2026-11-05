"""Git marks per file, from the index compared with the disk, in a real repository."""

import os
import shutil
import subprocess
import unittest

from tests.helpers import TempDirTestCase
from vulcan_celox.core import git_marks
from vulcan_celox.core.agents import repos
from vulcan_celox.core.runner import Runner

GIT = shutil.which("git")


def git(root, *args):
    subprocess.run(["git", "-C", str(root), "-c", "user.email=a@b.c", "-c", "user.name=x", "-c", "protocol.file.allow=always", *args],
                   check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)


@unittest.skipUnless(GIT and os.name != "nt", "git real")
class MarcasTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.repo = self.tmp / "repo"
        (self.repo / "pasta").mkdir(parents=True)
        git(self.repo, "init", "-q", "-b", "trabalho")
        for name in ("a.txt", "b.txt", "com espaço é.txt", "pasta/c.txt", "fica.txt"):
            (self.repo / name).write_text("um\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text("*.log\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "i")
        self.root = str(self.repo.resolve())

    def test_limpo(self):
        data = git_marks.collect(self.root)
        self.assertEqual((data["marks"], data["truncated"], data["branch"], data["repo"]), ({}, False, "trabalho", True))

    def test_alterado_novo_apagado_espaco_e_acento(self):
        (self.repo / "a.txt").write_text("outro tamanho\n", encoding="utf-8")
        (self.repo / "b.txt").unlink()
        (self.repo / "com espaço é.txt").write_text("mudou também\n", encoding="utf-8")
        (self.repo / "novo.txt").write_text("x", encoding="utf-8")
        (self.repo / "nova-pasta").mkdir()
        (self.repo / "nova-pasta" / "x.txt").write_text("x", encoding="utf-8")
        (self.repo / "ruido.log").write_text("x", encoding="utf-8")
        marks = git_marks.collect(self.root)["marks"]
        self.assertEqual(marks, {"a.txt": "M", "b.txt": "D", "com espaço é.txt": "M", "novo.txt": "U", "nova-pasta": "U"})
        real = subprocess.run(["git", "-C", self.root, "status", "--porcelain"], capture_output=True, text=True, check=True, timeout=30)
        self.assertEqual(repos.dirty_count(Runner(), self.root), len(real.stdout.splitlines()))
        (self.repo / "pasta-vazia").mkdir()  # git keeps no empty folder: the tree does not mark it
        self.assertNotIn("pasta-vazia", git_marks.collect(self.root)["marks"])

    def test_so_tocado_conta_como_alterado(self):
        future = (self.repo / "fica.txt").stat().st_mtime + 30
        os.utime(self.repo / "fica.txt", (future, future))
        self.assertEqual(git_marks.collect(self.root)["marks"], {"fica.txt": "M"})

    def test_subpasta_como_raiz(self):
        (self.repo / "pasta" / "c.txt").write_text("mudou muito\n", encoding="utf-8")
        (self.repo / "a.txt").write_text("fora da raiz\n", encoding="utf-8")
        self.assertEqual(git_marks.collect(str(self.repo / "pasta"))["marks"], {"c.txt": "M"})

    def test_submodulo_nao_conta(self):
        other = self.tmp / "outro"
        other.mkdir()
        git(other, "init", "-q")
        (other / "x.txt").write_text("x", encoding="utf-8")
        git(other, "add", "-A")
        git(other, "commit", "-qm", "i")
        git(self.repo, "submodule", "add", "-q", str(other), "sub")
        git(self.repo, "commit", "-qm", "sub")
        (self.repo / "sub" / "x.txt").write_text("mudou dentro\n", encoding="utf-8")
        self.assertNotIn("sub", git_marks.collect(self.root)["marks"])

    def test_indice_ausente(self):
        fresh = self.tmp / "novo"
        fresh.mkdir()
        git(fresh, "init", "-q", "-b", "main")
        (fresh / "a.txt").write_text("x", encoding="utf-8")
        data = git_marks.collect(str(fresh.resolve()))
        self.assertEqual((data["marks"], data["branch"]), ({"a.txt": "U"}, "main"))

    def test_fora_de_repositorio_e_core_worktree(self):
        solta = self.tmp / "solta"
        solta.mkdir()
        self.assertEqual(git_marks.collect(str(solta))["repo"], False)
        fora = self.tmp / "fora"
        fora.mkdir()
        (fora / "x.txt").write_text("x", encoding="utf-8")
        git(self.repo, "config", "core.worktree", str(fora))
        self.assertEqual(git_marks.collect(self.root)["marks"], {})

    def test_orcamento(self):
        for n in range(30):
            (self.repo / f"n{n}.txt").write_text("x", encoding="utf-8")
        data = git_marks.collect(self.root, limit=10)
        self.assertTrue(data["truncated"])
        self.assertLessEqual(len(data["marks"]), 10)


class ListagemTest(unittest.TestCase):
    def test_nome_entre_aspas(self):
        listing = '100644 abc 0\t"\\303\\251.txt"\n  ctime: 1:0\n  mtime: 1:0\n  dev: 1\tino: 1\n  uid: 1\tgid: 1\n  size: 3\tflags: 0\n'
        marks, cut = git_marks.index_marks("/nao/existe", listing)
        self.assertEqual((marks, cut), ({"é.txt": "D"}, False))


if __name__ == "__main__":
    unittest.main()
