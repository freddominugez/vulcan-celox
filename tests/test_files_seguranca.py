"""The analyzed repository is third-party. Redoes, with a repository that points filter, fsmonitor, textconv and external diff
at programs of its own, the proof of which git commands run them, and fails if a command used by the Code screen does."""

import os
import shutil
import subprocess
import unittest
from pathlib import Path
from urllib.parse import quote

from tests.server_helpers import ServerTestCase
from vulcan_celox.core.agents.repos import SAFE_GIT

GIT = shutil.which("git")
PROGRAM = """#!/bin/sh
echo "$0" >> "{log}"
cat
"""


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)


def malicious_repo(base: Path) -> Path:
    """Repository whose tracked file was changed keeping size (only then git has to run the clean filter to compare)."""
    repo = base / "repo"
    repo.mkdir()
    log = base / "executou.log"
    log.touch()
    tools = base / "programas"
    tools.mkdir()
    for name in ("filtro", "fsmonitor", "textconv", "externo", "ferramenta"):
        path = tools / name
        path.write_text(PROGRAM.format(log=log), encoding="utf-8")
        path.chmod(0o755)
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "a@b.c")
    git(repo, "config", "user.name", "x")
    (repo / ".gitattributes").write_text("*.txt filter=x diff=y\n", encoding="utf-8")
    (repo / ".gitignore").write_text("ignorado/\n", encoding="utf-8")
    (repo / "a.txt").write_text("procurado aaa\n", encoding="utf-8")
    (repo / "-traco.txt").write_text("-e valor\n", encoding="utf-8")
    (repo / ".env").write_text("procurado segredo\n", encoding="utf-8")
    (repo / "ignorado").mkdir()
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "inicio")
    git(repo, "config", "filter.x.clean", str(tools / "filtro"))
    git(repo, "config", "filter.x.smudge", str(tools / "filtro"))
    git(repo, "config", "core.fsmonitor", str(tools / "fsmonitor"))
    git(repo, "config", "diff.y.textconv", str(tools / "textconv"))
    git(repo, "config", "diff.external", str(tools / "externo"))
    git(repo, "config", "core.pager", str(tools / "ferramenta"))
    git(repo, "config", "core.sshCommand", str(tools / "ferramenta"))
    (repo / "a.txt").write_text("procurado bbb\n", encoding="utf-8")  # same size, other content
    future = (repo / "a.txt").stat().st_mtime + 10
    os.utime(repo / "a.txt", (future, future))
    return repo


@unittest.skipUnless(GIT and os.name != "nt", "prova com programas de shell e git")
class ProvaTest(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.base = self.tmp / "prova"
        self.base.mkdir()
        self.repo = malicious_repo(self.base)
        self.log = self.base / "executou.log"

    def runs(self, *argv):
        self.log.write_text("", encoding="utf-8")
        subprocess.run(argv, cwd=self.repo, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=30)
        return [Path(line).name for line in self.log.read_text(encoding="utf-8").splitlines()]

    def test_os_comandos_proibidos_executam(self):
        """If these ever stop running programs, the prohibition can be reviewed; while they run, they stay out."""
        self.assertIn("fsmonitor", self.runs("git", "status", "--porcelain"))
        self.assertIn("filtro", self.runs("git", "-c", "core.fsmonitor=false", "--no-optional-locks", "status", "--porcelain"))
        self.assertIn("filtro", self.runs("git", "-c", "core.fsmonitor=false", "ls-files", "-m"))

    def test_os_comandos_usados_nao_executam(self):
        self.assertEqual(self.runs("git", "-c", "core.fsmonitor=false", "ls-files", "-o", "-i", "--exclude-standard", "--directory"), [])
        self.assertEqual(self.runs("git", "-c", "core.fsmonitor=false", "grep", "--no-textconv", "-n", "-I", "procurado", "--", "."), [])
        self.assertEqual(self.runs(*SAFE_GIT, "cat-file", "blob", "HEAD:a.txt"), [])

    def test_o_fonte_nao_usa_comando_proibido(self):
        root = Path(__file__).resolve().parent.parent / "vulcan_celox"
        for name in ("core/file_tree.py", "core/file_watch.py", "core/git_marks.py", "server/files_api.py", "server/code_roots.py"):
            source = (root / name).read_text(encoding="utf-8")
            for word in ('"status"', '"diff"', '"-m"', "shell=True", "rev-list"):
                self.assertNotIn(word, source, name)

    def test_marcas_do_git_nao_executam(self):
        """Clean filter, fsmonitor pointing at a program, textconv: the marks come out and nothing runs."""
        from vulcan_celox.core import git_marks
        self.log.write_text("", encoding="utf-8")
        data = git_marks.collect(str(self.repo.resolve()))
        self.assertEqual(self.log.read_text(encoding="utf-8"), "")
        self.assertEqual(data["marks"], {"a.txt": "M"})

    def test_abrir_pelo_servidor_nao_executa_nada(self):
        """The whole Code screen against the malicious repository: tree, changes, read, diff and search."""
        root = str(self.repo.resolve())
        self.assertEqual(self.request("POST", "/api/files/roots", body={"path": root})[0], 200)
        self.log.write_text("", encoding="utf-8")
        q = quote(root)
        tree = self.request("GET", f"/api/files/tree?root={q}")[1]
        self.assertEqual({e["name"]: e["ignored"] for e in tree["entries"]}["ignorado"], True)
        self.assertEqual(self.request("GET", f"/api/files/changes?root={q}")[0], 200)
        self.assertEqual(self.request("GET", f"/api/files/read?root={q}&path=a.txt")[1]["text"], "procurado bbb\n")
        diff = self.request("GET", f"/api/files/diff?root={q}&path=a.txt")[1]
        self.assertEqual((diff["old"], diff["new"]), ("procurado aaa\n", "procurado bbb\n"))
        self.assertEqual(self.request("GET", f"/api/files/git?root={q}")[1]["marks"], {"a.txt": "M"})
        found = self.request("GET", f"/api/files/search?root={q}&q=procurado")[1]
        self.assertEqual([r["rel"] for r in found["results"]], ["a.txt"], "o .env fica de fora")
        dash = self.request("GET", f"/api/files/search?root={q}&q={quote('-e')}")
        self.assertEqual((dash[0], [r["rel"] for r in dash[1]["results"]]), (200, ["-traco.txt"]))
        self.app.files.stop()
        self.assertEqual(self.log.read_text(encoding="utf-8"), "")


def partial_clone(base: Path) -> Path:
    """A real partial clone: the blob is missing, and git would fetch it by itself."""
    origin = base / "o.git"
    seed = base / "semente"
    for args in (["init", "-q", "--bare", str(origin)], ["init", "-q", str(seed)]):
        subprocess.run(["git", *args], check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    git(origin, "config", "uploadpack.allowFilter", "true")
    git(origin, "symbolic-ref", "HEAD", "refs/heads/main")
    (seed / "a.txt").write_text("conteudo\n", encoding="utf-8")
    git(seed, "add", "-A")
    git(seed, "-c", "user.email=a@b.c", "-c", "user.name=x", "commit", "-qm", "i")
    git(seed, "push", "-q", str(origin), "HEAD:refs/heads/main")
    clone = base / "clone"
    subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout", f"file://{origin}", str(clone)], check=True,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    (clone / "a.txt").write_text("atual\n", encoding="utf-8")
    return clone


@unittest.skipUnless(GIT and os.name != "nt", "prova com programas de shell e git")
class ClonesParciaisTest(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.base = self.tmp / "parcial"
        self.base.mkdir()
        self.clone = partial_clone(self.base)
        self.log = self.base / "executou.log"
        self.log.touch()
        self.tool = self.base / "programa"
        # records and leaves at once: one that waits for input would hang git, which is the other half of the finding
        self.tool.write_text(f'#!/bin/sh\necho "$0" >> "{self.log}"\nexit 1\n', encoding="utf-8")
        self.tool.chmod(0o755)
        self.root = str(self.clone.resolve())
        self.request("POST", "/api/files/roots", body={"path": self.root})

    def proof(self, *config):
        for key, value in config:
            git(self.clone, "config", key, value)
        self.log.write_text("", encoding="utf-8")
        data = self.request("GET", f"/api/files/diff?root={quote(self.root)}&path=a.txt")[1]
        self.assertEqual(self.log.read_text(encoding="utf-8"), "", config)
        return data

    def test_controle_sem_a_defesa_o_programa_roda(self):
        git(self.clone, "config", "core.sshCommand", str(self.tool))
        git(self.clone, "config", "remote.origin.url", "ssh://evil.invalid/x.git")
        subprocess.run(["git", "-C", str(self.clone), "cat-file", "blob", "HEAD:a.txt"], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=False)
        self.assertNotEqual(self.log.read_text(encoding="utf-8"), "")

    def test_ssh(self):
        data = self.proof(("core.sshCommand", str(self.tool)), ("remote.origin.url", "ssh://evil.invalid/x.git"))
        self.assertEqual((data["available"], data["new"]), (True, "atual\n"))

    def test_ssh_com_protocolo_reaberto_pelo_repositorio(self):
        self.proof(("core.sshCommand", str(self.tool)), ("remote.origin.url", "ssh://evil.invalid/x.git"), ("protocol.ssh.allow", "always"), ("protocol.allow", "always"))

    def test_upload_pack(self):
        self.proof(("remote.origin.uploadpack", str(self.tool)), ("protocol.file.allow", "always"))

    def test_marcas_tambem(self):
        from vulcan_celox.core import git_marks
        git(self.clone, "config", "core.sshCommand", str(self.tool))
        git(self.clone, "config", "remote.origin.url", "ssh://evil.invalid/x.git")
        git(self.clone, "config", "remote.origin.uploadpack", str(self.tool))
        git(self.clone, "config", "core.fsmonitor", str(self.tool))
        self.log.write_text("", encoding="utf-8")
        self.assertTrue(git_marks.collect(self.root)["repo"])
        self.assertEqual(self.log.read_text(encoding="utf-8"), "")

    def test_git_state_tambem(self):
        from vulcan_celox.core.agents import repos
        from vulcan_celox.core.runner import Runner
        git(self.clone, "config", "core.sshCommand", str(self.tool))
        git(self.clone, "config", "remote.origin.url", "ssh://evil.invalid/x.git")
        self.assertTrue(repos.git_state(Runner(), self.root, worktrees=True).is_repo)
        self.assertEqual(self.log.read_text(encoding="utf-8"), "")


@unittest.skipUnless(GIT and os.name != "nt", "prova com programas de shell e git")
class TelaBranchesTest(ServerTestCase):
    def test_filtro_clean_nao_roda_e_a_contagem_bate(self):
        from vulcan_celox.core.agents import repos
        from vulcan_celox.core.runner import Runner
        base = self.tmp / "b"
        base.mkdir()
        repo = malicious_repo(base)
        log = base / "executou.log"
        log.write_text("", encoding="utf-8")
        state = repos.git_state(Runner(), str(repo))
        self.assertEqual(log.read_text(encoding="utf-8"), "", "abrir Branches executou programa do repositório")
        self.assertEqual(state.dirty, 1, "a.txt mudou, com o mesmo tamanho e outra data")

    def test_contagem_igual_a_do_git_status_sem_filtros(self):
        from vulcan_celox.core.agents import repos
        from vulcan_celox.core.runner import Runner
        repo = self.tmp / "normal"
        repo.mkdir()
        git(repo, "init", "-q")
        (repo / "sub").mkdir()
        for name in ("a.txt", "b.txt", "c.txt", "çã o.txt", "sub/d.txt"):
            (repo / name).write_text("um\n", encoding="utf-8")
        (repo / ".gitignore").write_text("*.log\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "-c", "user.email=a@b.c", "-c", "user.name=x", "commit", "-qm", "i")
        self.assertEqual(repos.git_state(Runner(), str(repo)).dirty, 0)
        (repo / "a.txt").write_text("outro tamanho\n", encoding="utf-8")
        (repo / "b.txt").unlink()
        (repo / "çã o.txt").write_text("mudou de novo\n", encoding="utf-8")
        (repo / "novo.txt").write_text("x", encoding="utf-8")
        (repo / "x.log").write_text("x", encoding="utf-8")
        real = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30, check=True)
        self.assertEqual(repos.git_state(Runner(), str(repo)).dirty, len(real.stdout.splitlines()))

    def test_core_worktree_nao_tira_a_busca_da_pasta(self):
        fora = self.tmp / "fora"
        fora.mkdir()
        (fora / "segredo.txt").write_text("SEGREDO_DE_FORA procurado\n", encoding="utf-8")
        repo = self.tmp / "aqui"
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "core.worktree", str(fora))
        git(repo, "add", "-A")
        root = str(repo.resolve())
        self.request("POST", "/api/files/roots", body={"path": root})
        data = self.request("GET", f"/api/files/search?root={quote(root)}&q=procurado")[1]
        self.assertEqual((data["available"], data["reason"]), (False, "no_repo"))

    def test_o_fonte_de_branches_nao_usa_git_status(self):
        source = (Path(__file__).resolve().parent.parent / "vulcan_celox" / "core" / "agents" / "repos.py").read_text(encoding="utf-8")
        self.assertNotIn('"status"', source)


if __name__ == "__main__":
    unittest.main()
