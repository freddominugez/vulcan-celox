"""GET /api/files/git: marks per file, cached per root, recalculated only after the sweep sees a change."""

import os
import shutil
import subprocess
import time
import unittest
from urllib.parse import quote

from tests.test_files_api import FilesCase
from vulcan_celox.server.files_api import GitMarksCache

GIT = shutil.which("git")


@unittest.skipUnless(GIT and os.name != "nt", "git real")
class RotaTest(FilesCase):
    def setUp(self):
        super().setUp()
        for args in (["init", "-q", "-b", "main"], ["add", "-A"]):
            subprocess.run(["git", "-C", self.root, *args], check=True, capture_output=True, timeout=30)
        (self.project / "a.txt").write_text("um\n", encoding="utf-8")
        subprocess.run(["git", "-C", self.root, "add", "-A"], check=True, capture_output=True, timeout=30)
        subprocess.run(["git", "-C", self.root, "-c", "user.email=a@b.c", "-c", "user.name=x", "commit", "-qm", "i"],
                       check=True, capture_output=True, timeout=30)

    def marks(self):
        status, data = self.get("git")[:2]
        self.assertEqual(status, 200)
        return data

    def test_marca_aparece_depois_da_varredura_e_git_nao_roda_sem_mudanca(self):
        first = self.marks()
        self.assertEqual((first["marks"], first["branch"], first["truncated"]), ({}, "main", False))
        runs = self.app.files.git.runs
        for _ in range(3):
            self.marks()
        self.assertEqual(self.app.files.git.runs, runs, "git rodou de novo sem mudança no disco")
        (self.project / "novo.txt").write_text("x", encoding="utf-8")
        (self.project / "a.txt").write_text("outro tamanho\n", encoding="utf-8")
        deadline = time.monotonic() + 8
        data = self.marks()
        while data["marks"] != {"novo.txt": "U", "a.txt": "M"} and time.monotonic() < deadline:
            time.sleep(0.3)
            data = self.marks()
        self.assertEqual(data["marks"], {"novo.txt": "U", "a.txt": "M"})
        self.assertGreater(self.app.files.git.runs, runs)

    def test_mesma_checagem_de_raiz(self):
        outside = self.tmp / "fora"
        outside.mkdir()
        status = self.request("GET", f"/api/files/git?root={quote(str(outside))}")[0]
        self.assertEqual(status, self.request("GET", f"/api/files/tree?root={quote(str(outside))}")[0])
        self.assertNotEqual(status, 200)


class CacheTest(unittest.TestCase):
    def test_validade_e_varredura(self):
        now = [0.0]
        calls = []
        cache = GitMarksCache(source=lambda root: calls.append(root) or {"n": len(calls)}, ttl=30, clock=lambda: now[0])
        self.assertEqual(cache.get("/r", 1), {"n": 1})
        self.assertEqual(cache.get("/r", 1), {"n": 1})
        now[0] = 29
        self.assertEqual(cache.get("/r", 1), {"n": 1})
        self.assertEqual(cache.get("/r", 2), {"n": 2}, "a varredura viu mudança")
        now[0] = 60
        self.assertEqual(cache.get("/r", 2), {"n": 3}, "passou o prazo")
        self.assertEqual(cache.runs, 3)


if __name__ == "__main__":
    unittest.main()
