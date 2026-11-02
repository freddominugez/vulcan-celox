"""vt-16 C8: branches e worktrees cruzando as sessões com o git real (só leitura)."""

import shutil
import unittest
from datetime import datetime, timezone

from tests import test_agents_api
from tests.helpers import TempDirTestCase
from vulcan_terminal.core.agents import repos
from vulcan_terminal.core.agents.model import AgentSession, FileTouch
from vulcan_terminal.core.runner import FakeRunner, Result, Runner

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
WRITE_VERBS = ("commit", "push", "add", "remove", "prune", "checkout", "reset", "stash")


SAFE = ["git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false", "--no-optional-locks"]


def git(path, *args):
    return [*SAFE, "-C", path, *args]


def repo(runner, path, branch="main", status="", ahead="0", worktrees=None):
    runner.respond(git(path, "rev-parse", "--is-inside-work-tree"), Result(0, "true\n"))
    runner.respond(git(path, "rev-parse", "--abbrev-ref", "HEAD"), Result(0, branch + "\n"))
    runner.respond(git(path, "status", "--porcelain"), Result(0, status))
    runner.respond(git(path, "rev-list", "--count", "@{u}..HEAD"),
                   Result(0, ahead + "\n") if ahead is not None else Result(128, "", "no upstream"))
    if worktrees is not None:
        runner.respond(git(path, "worktree", "list", "--porcelain"), Result(0, worktrees))


def session(sid, root, branch, published="none", edited=True, last="2026-10-30T11:00:00Z", agent="claude",
            worktree=None, pr=False):
    cwd = f"{root}/.claude/worktrees/{worktree}" if worktree else root
    return AgentSession(id=sid, agent=agent, file_path="/x", cwd=cwd, project_root=root,
                        project_name=root.rsplit("/", 1)[-1], git_branch=branch, worktree=worktree,
                        last_activity_at=last, published=published, pr_opened=pr,
                        files=[FileTouch(f"{cwd}/a.php", "edit")] if edited else [])


def rows(projects):
    return {(r["branch"], r["worktree"]): r for p in projects for r in p["rows"]}


class ReposTest(unittest.TestCase):
    def setUp(self):
        self.runner = FakeRunner(default=Result(128, "", "not a git repository"))

    def build(self, sessions):
        return repos.build(sessions, self.runner, now=NOW)

    def test_limpo_e_publicado(self):
        repo(self.runner, "/dev/loja", worktrees="worktree /dev/loja\nbranch refs/heads/main\n")
        r = rows(self.build([session("s1", "/dev/loja", "main", published="pushed")]))[("main", None)]
        self.assertEqual((r["state"], r["dirty"], r["ahead"]), ("publicado", 0, 0))

    def test_sujo_e_sem_commit(self):
        repo(self.runner, "/dev/loja", status=" M app/a.php\n?? novo.php\n")
        r = rows(self.build([session("s1", "/dev/loja", "main")]))[("main", None)]
        self.assertEqual((r["state"], r["dirty"]), ("sem commit", 2))

    def test_a_frente_do_remoto(self):
        repo(self.runner, "/dev/loja", ahead="2")
        r = rows(self.build([session("s1", "/dev/loja", "main", published="committed")]))[("main", None)]
        self.assertEqual((r["state"], r["ahead"]), ("sem push", 2))

    def test_sem_upstream(self):
        repo(self.runner, "/dev/loja", branch="feat/x", ahead=None)
        r = rows(self.build([session("s1", "/dev/loja", "feat/x", published="committed")]))[("feat/x", None)]
        self.assertEqual(r["state"], "sem upstream")

    def test_pasta_sem_git(self):
        projects = self.build([session("s1", "/dev/solto", None)])
        self.assertFalse(projects[0]["is_repo"])
        self.assertEqual(projects[0]["rows"][0]["state"], "sem git")

    def test_branch_do_codex_vem_do_git(self):
        repo(self.runner, "/dev/clerk", branch="feature/gravacao")
        r = rows(self.build([session("c1", "/dev/clerk", None, agent="codex", published="pushed")]))
        self.assertIn(("feature/gravacao", None), r)

    def test_branch_fechado_usa_o_registro_das_sessoes(self):
        repo(self.runner, "/dev/loja", branch="main")
        r = rows(self.build([session("s1", "/dev/loja", "feat/antigo", published="committed")]))[("feat/antigo", None)]
        self.assertEqual(r["state"], "sem push")
        self.assertIsNone(r["dirty"])

    def test_worktree_parada_e_worktree_orfa(self):
        wt = "/dev/loja/.claude/worktrees/relatorio"
        listing = (f"worktree /dev/loja\nbranch refs/heads/main\n\nworktree {wt}\nbranch refs/heads/feat/relatorio\n\n"
                   "worktree /dev/loja/.claude/worktrees/esquecida\nbranch refs/heads/feat/esquecida\nprunable gitdir file points to non-existent location\n")
        repo(self.runner, "/dev/loja", worktrees=listing)
        repo(self.runner, wt, branch="feat/relatorio", status=" M r.php\n")
        repo(self.runner, "/dev/loja/.claude/worktrees/esquecida", branch="feat/esquecida")
        old = session("s1", "/dev/loja", "feat/relatorio", worktree="relatorio", last="2026-10-24T16:00:00Z")
        r = rows(self.build([old]))
        stale = r[("feat/relatorio", "relatorio")]
        self.assertEqual((stale["state"], stale["stale_days"], stale["dirty"]), ("sem commit", 5, 1))
        orphan = r[("feat/esquecida", "esquecida")]
        self.assertTrue(orphan["orphan_worktree"])
        self.assertEqual(orphan["sessions"], [])
        self.assertEqual(list(r)[0], ("feat/relatorio", "relatorio"))  # a pior situação primeiro

    def test_so_comandos_de_leitura(self):
        repo(self.runner, "/dev/loja", status=" M a\n", worktrees="")
        self.build([session("s1", "/dev/loja", "main")])
        self.assertTrue(self.runner.calls)
        for call in self.runner.calls:
            # vt-16b C4: sem fsmonitor nem untrackedCache, o git status não executa programa do repositório analisado
            self.assertEqual(list(call.argv[:len(SAFE)]), SAFE)
            verb = call.argv[len(SAFE) + 2]
            self.assertNotIn(verb, WRITE_VERBS, call.argv)

    def test_parse_worktrees(self):
        out = repos.parse_worktrees("worktree /a\nHEAD abc\nbranch refs/heads/main\n\nworktree /b\ndetached\n")
        self.assertEqual(out, [{"path": "/a", "branch": "main"}, {"path": "/b", "detached": "true"}])


class ReposApiTest(test_agents_api.AgentsServerCase):
    def test_rota(self):
        data = self.get("/api/agents/repos")
        self.assertEqual({p["project"] for p in data["projects"]}, {"projeto", "clerk", "loja"})
        self.assertTrue(all(r["state"] == "sem git" for p in data["projects"] for r in p["rows"]))


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(shutil.which("git"), "git ausente")
class FsmonitorRealTest(TempDirTestCase):
    """Prova com git de verdade: um core.fsmonitor do repositório analisado não é executado."""

    def test_hook_do_repositorio_nao_roda(self):
        repo_dir, marker = self.tmp / "repo", self.tmp / "executou"
        repo_dir.mkdir()
        hook = self.tmp / "hook.sh"
        hook.write_text(f"#!/bin/sh\ntouch {marker}\n")
        hook.chmod(0o755)
        runner = Runner()
        runner.run(["git", "init", "-q", str(repo_dir)])
        runner.run(["git", "-C", str(repo_dir), "config", "core.fsmonitor", str(hook)])
        (repo_dir / "a.txt").write_text("x")
        state = repos.git_state(runner, str(repo_dir))
        self.assertTrue(state.is_repo)
        self.assertEqual(state.dirty, 1)
        self.assertFalse(marker.exists(), "o git status executou o core.fsmonitor do repositório")
        runner.run(["git", "-C", str(repo_dir), "status", "--porcelain"])  # controle: sem a defesa, o hook roda
        self.assertTrue(marker.exists())


class WorktreeSubpastaTest(unittest.TestCase):
    def test_sessao_numa_subpasta_usa_a_raiz_da_worktree(self):
        runner = FakeRunner(default=Result(128, "", "not a git repository"))
        wt = "/dev/loja/.claude/worktrees/feat"
        repo(runner, "/dev/loja", worktrees=f"worktree /dev/loja\nbranch refs/heads/main\n\nworktree {wt}\nbranch refs/heads/feat\n")
        repo(runner, wt, branch="feat", status=" M a\n")
        s = session("s1", "/dev/loja", "feat", worktree="feat")
        s.cwd = f"{wt}/src"
        r = rows(repos.build([s], runner, now=NOW))
        self.assertEqual(list(r), [("feat", "feat")])
        self.assertEqual(r[("feat", "feat")]["path"], wt)
        self.assertFalse(r[("feat", "feat")]["orphan_worktree"])
        self.assertEqual(r[("feat", "feat")]["state"], "sem commit")
