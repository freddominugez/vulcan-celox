"""Session code roots, observer clients, and diff base evidence."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode

from tests.server_helpers import ServerTestCase
from tests.test_files_seguranca import git
from vulcan_celox.core.file_tree import Ignored
from vulcan_celox.core.file_watch import RootWatch


class WatchScopeTest(unittest.TestCase):
    def test_pastas_distintas_e_substituicao_de_pasta(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = base / "projeto"
            for folder in [root / "a", root / "b", base / "fora"]:
                folder.mkdir(parents=True)
            watch = RootWatch(str(root), lambda _: Ignored(), 0, budget=1)
            watch.sweep()
            self.assertTrue(watch.partial)
            a = watch.poll(None, ["a"], "", client="a")["cursor"]
            b = watch.poll(None, ["b"], "", client="b")["cursor"]
            watch.sweep()
            (root / "a" / "novo.txt").write_text("a", encoding="utf-8")
            (root / "b" / "novo.txt").write_text("b", encoding="utf-8")
            watch.sweep()
            self.assertEqual([e["rel"] for e in watch.poll(a, ["a"], "", client="a")["events"]], ["a/novo.txt"])
            self.assertEqual([e["rel"] for e in watch.poll(b, ["b"], "", client="b")["events"]], ["b/novo.txt"])
            if os.name == "nt":
                return
            (root / "a").rename(base / "anterior")
            (root / "a").symlink_to(base / "fora", target_is_directory=True)
            (base / "fora" / "privado.txt").write_text("fora", encoding="utf-8")
            watch.sweep()
            self.assertNotIn("a/privado.txt", watch.photo_files())


@unittest.skipUnless(shutil.which("git"), "sem git")
class CodeContextTest(ServerTestCase):
    def test_head_valido_e_worktree_que_exige_abertura_explicita(self):
        project = self.tmp / "repo"
        project.mkdir()
        git(project, "init", "-q")
        (project / "a.txt").write_text("atual", encoding="utf-8")
        root = str(project.resolve())
        self.request("POST", "/api/files/roots", body={"path": root})
        query = urlencode({"root": root, "path": "a.txt"})
        diff = self.request("GET", f"/api/files/diff?{query}")[1]
        self.assertEqual(diff["reason"], "previous_unavailable")
        git(project, "-c", "user.email=fixture@example.invalid", "-c", "user.name=Fixture",
            "commit", "--allow-empty", "-qm", "base")
        diff = self.request("GET", f"/api/files/diff?{query}")[1]
        self.assertEqual(diff["status"], "new")
        self.assertEqual(len(diff["base"]), 40)
        worktree = project / "worktree"
        git(project, "worktree", "add", "--detach", str(worktree), "HEAD")
        (worktree / "sub").mkdir()
        response = self.request("POST", "/api/terminals", body={"cwd": str(worktree / "sub")})[1]
        url = "/api/files/roots?" + urlencode({"terminal": response["id"]})
        self.assertIsNone(self.request("GET", url)[1]["context"]["root"])
        self.request("POST", "/api/files/roots", body={"path": str(worktree)})
        self.assertEqual(self.request("GET", url)[1]["context"]["root"], str(worktree.resolve()))
