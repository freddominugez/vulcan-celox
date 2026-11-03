"""Variáveis dos prompts a partir da sessão de agente."""

import unittest

from vulcan_terminal.core import prompts
from vulcan_terminal.core.agents.model import AgentSession
from vulcan_terminal.core.agents.repos import SAFE_GIT
from vulcan_terminal.core.runner import FakeRunner, Result


def git(path, *args):
    return [*SAFE_GIT, "-C", path, *args]


def session(**kw):
    base = dict(id="7f3c9a21-4b0e", agent="claude", file_path="/x", cwd="/Users/dev/loja", project_root="/Users/dev/loja",
                project_name="loja", git_branch="feat/frete")
    base.update(kw)
    return AgentSession(**base)


class ContextTest(unittest.TestCase):
    def test_variaveis_da_sessao_e_base_do_remoto(self):
        runner = FakeRunner(default=Result(128, "", "erro"))
        runner.respond(git("/Users/dev/loja", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"), Result(0, "origin/develop\n"))
        ctx = prompts.context_for(session(), runner)
        self.assertEqual(ctx, {"sessionId": "7f3c9a21-4b0e", "branch": "feat/frete", "base": "develop",
                               "projectName": "loja", "cwd": "/Users/dev/loja", "agent": "Claude Code"})

    def test_base_reserva_main(self):
        ctx = prompts.context_for(session(), FakeRunner(default=Result(128, "", "sem remoto")))
        self.assertEqual(ctx["base"], "main")

    def test_branch_do_codex_vem_do_git(self):
        runner = FakeRunner(default=Result(128, "", "erro"))
        runner.respond(git("/Users/dev/clerk", "rev-parse", "--abbrev-ref", "HEAD"), Result(0, "feature/gravacao\n"))
        ctx = prompts.context_for(session(agent="codex", git_branch=None, cwd="/Users/dev/clerk", project_name="clerk"), runner)
        self.assertEqual((ctx["branch"], ctx["agent"]), ("feature/gravacao", "Codex"))

    def test_worktree_usa_a_pasta_da_worktree(self):
        runner = FakeRunner(default=Result(128, "", "erro"))
        prompts.context_for(session(cwd="/Users/dev/loja/.claude/worktrees/cupom/src", worktree="cupom"), runner)
        self.assertTrue(all("/Users/dev/loja/.claude/worktrees/cupom" in c.argv for c in runner.calls))

    def test_sem_sessao(self):
        self.assertEqual(prompts.context_for(None, FakeRunner()), {})

    def test_so_git_de_leitura(self):
        runner = FakeRunner(default=Result(128, "", "erro"))
        prompts.context_for(session(git_branch=None), runner)
        for call in runner.calls:
            self.assertEqual(list(call.argv[:len(SAFE_GIT)]), list(SAFE_GIT))
            self.assertIn(call.argv[len(SAFE_GIT) + 2], ("symbolic-ref", "rev-parse"))


class ChooseTest(unittest.TestCase):
    def test_escolhida_ativa_e_mais_recente(self):
        old = session(id="a", last_activity_at="2026-10-31T08:00:00Z")
        active = session(id="b", last_activity_at="2026-10-31T07:00:00Z", is_active=True)
        recent = session(id="c", last_activity_at="2026-10-31T09:00:00Z")
        listing = [recent, old, active]  # o índice lista da mais recente para a mais antiga
        self.assertEqual(prompts.choose_current(listing, None).id, "b")       # ativa primeiro
        self.assertEqual(prompts.choose_current([recent, old], None).id, "c")  # sem ativa: a mais recente
        self.assertEqual(prompts.choose_current(listing, "a").id, "a")        # escolhida pelo usuário
        self.assertEqual(prompts.choose_current(listing, "sumiu").id, "b")    # escolhida sumiu: automático
        self.assertIsNone(prompts.choose_current([], None))
