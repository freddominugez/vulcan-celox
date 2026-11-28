"""A folder above the approved root that can be traversed but not read (0111, 0311): the tree, the reader, the diff and
the live watch keep working, and a root swapped for a link is still refused."""

import os
import shutil
import subprocess
import time
import unittest
from pathlib import Path
from urllib.parse import urlencode

from tests.helpers import TempDirTestCase
from tests.server_helpers import ServerTestCase
from vulcan_celox.core import code_boundary
from vulcan_celox.core.file_tree import Ignored
from vulcan_celox.core.file_watch import RootWatch

POSIX_DIR_FD = os.name != "nt" and os.open in os.supports_dir_fd and os.scandir in os.supports_fd
AS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0
needs_unreadable_parent = unittest.skipUnless(POSIX_DIR_FD and not AS_ROOT,
                                              "exige permissões POSIX efetivas (não Windows, não root)")


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", *args],
                   check=True, capture_output=True)


class GateMixin:
    def make_gate(self, base: Path):
        self.gate = base.resolve() / "gate"
        self.proj = self.gate / "proj"
        (self.proj / "sub").mkdir(parents=True)
        (self.proj / "a.txt").write_text("linha antiga\n", encoding="utf-8")
        (self.proj / "sub" / "b.txt").write_text("b\n", encoding="utf-8")
        self.addCleanup(os.chmod, self.gate, 0o755)  # before the temporary folder is removed

    def close_gate(self, mode=0o111):
        os.chmod(self.gate, mode)
        with self.assertRaises(PermissionError):
            os.listdir(self.gate)  # the scenario is real: the parent cannot be read


@needs_unreadable_parent
class BoundaryUnitTest(GateMixin, TempDirTestCase):
    def test_sem_raiz_continua_falhando_fechado_como_antes(self):
        self.make_gate(self.tmp)
        self.close_gate()
        with self.assertRaises(PermissionError):
            with code_boundary.directory(self.proj):
                pass

    def test_com_raiz_abre_a_raiz_e_o_que_esta_abaixo(self):
        self.make_gate(self.tmp)
        self.close_gate()
        with code_boundary.directory(self.proj, self.proj) as fd:
            self.assertEqual(sorted(os.listdir(fd)), ["a.txt", "sub"])
        with code_boundary.directory(self.proj / "sub", self.proj) as fd:
            self.assertEqual(os.listdir(fd), ["b.txt"])
        fd = code_boundary.open_file(self.proj / "sub" / "b.txt", os.O_RDONLY, root=self.proj)
        try:
            self.assertEqual(os.read(fd, 10), b"b\n")
        finally:
            os.close(fd)

    def test_raiz_ilegivel_nao_e_contornada(self):
        self.make_gate(self.tmp)
        os.chmod(self.proj, 0o311)
        self.addCleanup(os.chmod, self.proj, 0o755)
        with self.assertRaises(PermissionError):
            with code_boundary.directory(self.proj, self.proj):
                pass

    def test_link_abaixo_da_raiz_nao_e_seguido(self):
        self.make_gate(self.tmp)
        fora = self.tmp.resolve() / "fora"
        fora.mkdir()
        (fora / "segredo.txt").write_text("SEGREDO_FORA", encoding="utf-8")
        shutil.rmtree(self.proj / "sub")
        os.symlink(fora, self.proj / "sub")
        self.close_gate()
        with self.assertRaises(OSError):
            with code_boundary.directory(self.proj / "sub", self.proj):
                pass

    def test_raiz_trocada_por_link_e_recusada_no_ramo_ancorado(self):
        self.make_gate(self.tmp)
        fora = self.tmp.resolve() / "fora"
        fora.mkdir()
        os.rename(self.proj, self.gate / "proj.antiga")
        os.symlink(fora, self.proj)
        self.close_gate(0o311)
        with self.assertRaises(OSError):
            with code_boundary.directory(self.proj, self.proj):
                pass


@needs_unreadable_parent
class AncestorApiTest(GateMixin, ServerTestCase):
    def get(self, url, **args):
        return self.request("GET", url + "?" + urlencode(args))[:2]

    def test_arvore_leitura_e_diff_com_pasta_mae_so_com_execucao(self):
        self.make_gate(self.tmp)
        git(self.proj, "init", "-q")
        git(self.proj, "add", ".")
        git(self.proj, "commit", "-qm", "base")
        (self.proj / "a.txt").write_text("linha nova\n", encoding="utf-8")
        root = str(self.proj)
        status, body = self.request("POST", "/api/files/roots", body={"path": root})[:2]
        self.assertEqual(status, 200, body)
        self.close_gate()

        status, tree = self.get("/api/files/tree", root=root, path="")
        self.assertEqual(status, 200, tree)
        self.assertEqual([e["name"] for e in tree["entries"]], ["sub", "a.txt"])
        status, sub = self.get("/api/files/tree", root=root, path="sub")
        self.assertEqual((status, [e["name"] for e in sub["entries"]]), (200, ["b.txt"]))
        status, read = self.get("/api/files/read", root=root, path="a.txt")
        self.assertEqual((status, read.get("text")), (200, "linha nova\n"))
        status, diff = self.get("/api/files/diff", root=root, path="a.txt")
        self.assertEqual(status, 200, diff)
        self.assertEqual((diff["available"], diff["status"], diff["old"], diff["new"]),
                         (True, "modified", "linha antiga\n", "linha nova\n"))

    def test_raiz_trocada_por_link_continua_403(self):
        self.make_gate(self.tmp)
        fora = self.tmp.resolve() / "fora"
        fora.mkdir()
        (fora / "segredo.txt").write_text("SEGREDO_FORA", encoding="utf-8")
        root = str(self.proj)
        self.assertEqual(self.request("POST", "/api/files/roots", body={"path": root})[0], 200)
        os.rename(root, root + ".bak")
        os.symlink(fora, root)
        self.close_gate(0o311)
        for route in ("/api/files/read", "/api/files/tree", "/api/files/diff"):
            with self.subTest(route=route):
                status, body = self.get(route, root=root, path="segredo.txt" if route != "/api/files/tree" else "")
                self.assertEqual(status, 403, body)
                self.assertNotIn("SEGREDO_FORA", str(body))


@needs_unreadable_parent
class AncestorWatchTest(GateMixin, TempDirTestCase):
    def test_observador_ve_arquivo_criado_com_pasta_mae_so_com_execucao(self):
        self.make_gate(self.tmp)
        self.close_gate()
        watch = RootWatch(str(self.proj), lambda _root: Ignored(set()), 1, low=0.02, high=0.05)
        watch.start()
        self.addCleanup(lambda: (watch.stop(), watch.thread.join(3)))
        self.assertTrue(watch.ready.wait(5))
        cursor = watch.poll(None, [], "")["cursor"]
        self.assertIn("a.txt", watch.photo_files())
        (self.proj / "novo.txt").write_text("x", encoding="utf-8")
        deadline, got = time.monotonic() + 4, []
        while time.monotonic() < deadline and not got:
            data = watch.poll(cursor, [], "")
            got, cursor = data["events"], data["cursor"]
            time.sleep(0.02)
        self.assertEqual([(e["rel"], e["change"]) for e in got], [("novo.txt", "added")])


if __name__ == "__main__":
    unittest.main()
