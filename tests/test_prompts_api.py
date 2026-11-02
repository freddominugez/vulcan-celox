"""vt-17 C3: rotas dos prompts, criação com confirmação para a pasta do projeto e abertura só de arquivos de prompt."""

from pathlib import Path

from tests import test_agents_api
from vulcan_terminal.core import prompts

CLAUDE_SID = "11111111-2222-4333-8444-555555555555"


class PromptsApiTest(test_agents_api.AgentsServerCase):
    def setUp(self):
        super().setUp()
        self.global_dir = Path(self.app.data_dir) / "prompts"

    def post(self, path, body):
        status, data, _ = self.request("POST", path, body=body)
        return status, data

    def test_exemplos_criados_e_renderizados_com_a_sessao_atual(self):
        data = self.get("/api/prompts")
        self.assertTrue(self.global_dir.is_dir())
        self.assertEqual(data["session"]["id"], CLAUDE_SID)
        by_id = {p["id"]: p for p in data["prompts"]}
        self.assertIn(f"sessão {CLAUDE_SID}", by_id["seguranca"]["rendered"])
        self.assertIn("projeto projeto", by_id["seguranca"]["rendered"])
        self.assertEqual(by_id["seguranca"]["missing"], [])
        self.assertEqual([c["name"] for c in data["categories"]][:5], prompts.DEFAULT_CATEGORIES)
        self.assertFalse(data["project"]["exists"])
        self.assertEqual(data["project"]["dir"], "/Users/dev/projeto/.vulcan/prompts")

    def test_sessao_escolhida_e_desconhecida(self):
        codex = "019a0000-1111-7222-8333-444444444444"
        data = self.get(f"/api/prompts?session={codex}")
        self.assertEqual(data["context"]["agent"], "Codex")
        status, _, _ = self.request("GET", "/api/prompts?session=nao-existe")
        self.assertEqual(status, 404)

    def test_prompts_fixados_pela_pasta_do_terminal(self):
        data = self.get("/api/prompts?pinned=1&cwd=/Users/dev/loja")
        self.assertTrue(data["prompts"])
        self.assertTrue(all(p["pin"] for p in data["prompts"]))
        self.assertEqual(data["session"]["project"], "loja")  # a sessão mais recente daquela pasta

    def test_criar_prompt_global_e_categoria(self):
        self.get("/api/prompts")
        status, data = self.post("/api/prompts/categories", {"name": "Laravel"})
        self.assertEqual(status, 200)
        status, data = self.post("/api/prompts", {"title": "Rodar filas", "category": "Laravel", "scope": "global"})
        self.assertEqual(status, 200)
        self.assertTrue(Path(data["path"]).is_file())
        names = {c["name"]: c for c in self.get("/api/prompts")["categories"]}
        self.assertTrue(names["Laravel"]["user"])
        self.assertEqual(names["Laravel"]["count"], 1)

    def test_prompt_do_projeto_pede_confirmacao_para_criar_a_pasta(self):
        project = self.tmp / "loja-real"
        project.mkdir()
        self.app.store.save("node_projects", {"loja-real": str(project)})  # pasta conhecida (vt-28 C2)
        body = {"title": "Só neste projeto", "category": "Testes", "scope": "project", "project_root": str(project)}
        status, data = self.post("/api/prompts", body)
        self.assertEqual((status, data.get("needs_confirmation")), (409, True))
        self.assertFalse((project / ".vulcan").exists())
        status, data = self.post("/api/prompts", {**body, "confirm_project_dir": True})
        self.assertEqual(status, 200)
        self.assertTrue(Path(data["path"]).is_relative_to(project / ".vulcan" / "prompts"))

    def test_pasta_desconhecida_ou_dos_agentes_recusada(self):
        """vt-28 C2: project_root precisa ser site, projeto Node ou sessão; nunca a pasta de dados de um agente."""
        stranger = self.tmp / "qualquer"
        stranger.mkdir()
        claude = self.tmp / "claude-home"
        claude.mkdir(exist_ok=True)
        self.app.store.save("node_projects", {"claude": str(claude)})
        from unittest import mock
        from vulcan_terminal.core.agents import discovery
        with mock.patch.object(discovery, "claude_root", return_value=claude):
            for root in (stranger, claude):
                for path in ("/api/prompts", "/api/prompts/categories"):
                    with self.subTest(root=root.name, path=path):
                        status, _ = self.post(path, {"title": "x", "name": "x", "scope": "project",
                                                     "project_root": str(root), "confirm_project_dir": True})
                        self.assertEqual(status, 400)
        self.assertFalse((stranger / ".vulcan").exists())
        self.assertFalse((claude / ".vulcan").exists())

    def test_cabecalho_nao_aceita_injecao_e_preserva_o_titulo(self):
        path = prompts.create_prompt(self.tmp / "p", "Deploy: prod #1 'x'", "Seg\npin: true")
        prompt, warning = prompts.parse_file(path, "global", "Geral")
        self.assertIsNone(warning)
        self.assertEqual(prompt.title, "Deploy: prod #1 'x'")
        self.assertEqual(prompt.category, "Seg pin: true")
        self.assertFalse(prompt.pin)

    def test_validacao(self):
        for body in ({"title": "x", "scope": "outro"}, {"title": 5, "scope": "global"},
                     {"title": "x", "scope": "project", "project_root": "/nao/existe/mesmo"}):
            with self.subTest(body=body):
                status, _ = self.post("/api/prompts", body)
                self.assertEqual(status, 400)

    def test_abrir_so_arquivo_de_prompt(self):
        self.get("/api/prompts")
        prompt_file = next(self.global_dir.rglob("*.md"))
        status, _ = self.post("/api/open", {"kind": "prompt", "target": str(prompt_file)})
        self.assertEqual(status, 200)
        self.assertTrue(any(str(prompt_file.resolve()) in call.argv for call in self.fake.calls))
        other = self.tmp / "segredo.md"
        other.write_text("x")
        for target in (str(other), str(self.global_dir / ".." / "segredo.md"), str(self.global_dir)):
            with self.subTest(target=target):
                status, _ = self.post("/api/open", {"kind": "prompt", "target": target})
                self.assertEqual(status, 400)
