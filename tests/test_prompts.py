"""Prompts em Markdown com cabeçalho, globais e por projeto, renderizados com as variáveis da sessão."""

from tests.helpers import TempDirTestCase
from vulcan_celox.core import prompts


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class SeedTest(TempDirTestCase):
    def test_exemplos_criados_uma_vez_nas_cinco_categorias(self):
        root = self.tmp / "prompts"
        created = prompts.seed_global(root)
        self.assertGreaterEqual(len(created), 5)
        loaded, warnings = prompts.load_dir(root, "global")
        self.assertEqual(warnings, [])
        self.assertTrue(set(prompts.DEFAULT_CATEGORIES) <= {p.category for p in loaded})
        self.assertTrue(any(p.pin for p in loaded))
        self.assertTrue(all("—" not in p.body for p in loaded))
        edited = loaded[0].path
        edited.write_text(edited.read_text(encoding="utf-8") + "\nmeu ajuste\n", encoding="utf-8")
        self.assertEqual(prompts.seed_global(root), [])  # pasta já existe: nunca sobrescreve
        self.assertIn("meu ajuste", edited.read_text(encoding="utf-8"))


class LoadTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.g = self.tmp / "global"
        self.p = self.tmp / "loja" / ".vulcan" / "prompts"
        write(self.g / "seguranca.md", "---\nid: seguranca\ntitle: Regras do branch\ncategory: Segurança\npin: true\n---\n"
                                       "Você está no branch {{branch}} do projeto {{projectName}}.\n")
        write(self.g / "Testes" / "loop.md", "---\nid: loop\ntitle: Sair do loop\n---\nPare de rodar {{ teste }}.\n")
        write(self.g / "sem-cabecalho.md", "Texto puro para {{cwd}}.\n")
        write(self.g / "quebrado.md", "---\nid: x\n  title: indentação errada\n---\ncorpo\n")
        write(self.g / "sem-fim.md", "---\nid: x\ntitle: nunca fecha\ncorpo\n")
        write(self.g / "notas.txt", "não é prompt")
        write(self.p / "seguranca.md", "---\nid: seguranca\ntitle: Regras deste projeto\ncategory: Segurança\n---\nNa loja, {{branch}} é sagrado.\n")
        write(self.p / "Laravel" / "artisan.md", "---\ntitle: Rodar artisan\n---\nphp artisan {{comando}}\n")

    def test_campos_categoria_e_avisos(self):
        loaded, warnings = prompts.load_dir(self.g, "global")
        by_id = {p.id: p for p in loaded}
        self.assertEqual(set(by_id), {"seguranca", "loop", "sem-cabecalho"})
        self.assertEqual((by_id["seguranca"].title, by_id["seguranca"].category, by_id["seguranca"].pin),
                         ("Regras do branch", "Segurança", True))
        self.assertEqual(by_id["loop"].category, "Testes")             # pela subpasta
        self.assertEqual(by_id["sem-cabecalho"].title, "Sem cabecalho")  # do nome do arquivo
        self.assertEqual(by_id["sem-cabecalho"].category, "Outros")
        self.assertEqual(sorted(w.split(":")[0] for w in warnings), ["quebrado.md", "sem-fim.md"])

    def test_projeto_sobrescreve_global_pelo_id(self):
        merged, _ = prompts.load_all(self.g, self.p)
        by_id = {p.id: p for p in merged}
        self.assertEqual(by_id["seguranca"].title, "Regras deste projeto")
        self.assertEqual((by_id["seguranca"].scope, by_id["seguranca"].overrides), ("project", True))
        self.assertEqual((by_id["artisan"].scope, by_id["artisan"].category), ("project", "Laravel"))
        self.assertEqual(by_id["loop"].scope, "global")
        self.assertEqual(len(merged), 4)

    def test_sem_pasta_de_projeto(self):
        merged, warnings = prompts.load_all(self.g, self.tmp / "nao-existe")
        self.assertEqual({p.scope for p in merged}, {"global"})


class RenderTest(TempDirTestCase):
    def test_variaveis_e_ausentes(self):
        text, missing = prompts.render("Branch {{branch}}, de novo {{ branch }}, ticket {{ticket}} e {{ticket}}.",
                                       {"branch": "feat/x", "projectName": "loja"})
        self.assertEqual(text, "Branch feat/x, de novo feat/x, ticket {{ticket}} e {{ticket}}.")
        self.assertEqual(missing, ["ticket"])

    def test_sem_logica(self):
        text, missing = prompts.render("{{#if x}}{{x.y}}{{/if}}", {"x": "1"})
        self.assertEqual(text, "{{#if x}}{{x.y}}{{/if}}")
        self.assertEqual(missing, [])


class CreateTest(TempDirTestCase):
    def test_cria_prompt_sem_sobrescrever(self):
        root = self.tmp / "prompts"
        first = prompts.create_prompt(root, "Rodar só os testes do módulo", "Testes")
        second = prompts.create_prompt(root, "Rodar só os testes do módulo", "Testes")
        self.assertEqual(first, root / "testes" / "rodar-so-os-testes-do-modulo.md")
        self.assertEqual(second.name, "rodar-so-os-testes-do-modulo-2.md")
        loaded, warnings = prompts.load_dir(root, "global")
        self.assertEqual(warnings, [])
        self.assertEqual({p.title for p in loaded}, {"Rodar só os testes do módulo"})
        self.assertEqual({p.category for p in loaded}, {"Testes"})
        self.assertEqual(len({p.id for p in loaded}), 2)

    def test_cria_categoria(self):
        root = self.tmp / "prompts"
        path = prompts.create_category(root, "Laravel / Filas")
        self.assertEqual(path, root / "laravel-filas")
        self.assertTrue(path.is_dir())
        self.assertEqual(prompts.categories(root), ["Laravel / Filas"])

    def test_nomes_nao_escapam_da_pasta(self):
        root = self.tmp / "prompts"
        for evil in ("../../fora", "/etc/passwd", "..", ""):
            with self.subTest(evil=evil):
                path = prompts.create_prompt(root, evil or "x", evil)
                self.assertTrue(path.resolve().is_relative_to(root.resolve()) if hasattr(path, "is_relative_to")
                                else str(path.resolve()).startswith(str(root.resolve())))

    def test_pasta_do_projeto(self):
        self.assertEqual(prompts.project_dir("/Users/dev/loja").as_posix(), "/Users/dev/loja/.vulcan/prompts")


class CardTest(TempDirTestCase):
    """O cartão diz o que o prompt faz, sem `{{nome}}`."""

    def load(self, text):
        path = self.tmp / "p.md"
        path.write_text(text, encoding="utf-8")
        prompt, warning = prompts.parse_file(path, "global", "Outros")
        self.assertIsNone(warning)
        return prompt

    def test_com_descricao_e_icone(self):
        p = self.load("---\ntitle: Publicar\ndescricao: Abre o PR de {{branch}} contra a base.\nicone: branch\n---\n"
                      "Rode a suíte. Faça push de {{branch}} e abra o PR contra {{base}}.\n")
        self.assertEqual(p.icon, "branch")
        self.assertEqual(prompts.summary(p, {"branch": "feat/x"}), "Abre o PR de feat/x contra a base.")
        self.assertEqual(p.to_dict()["variables"], ["branch", "base"])

    def test_sem_descricao_usa_a_primeira_frase(self):
        p = self.load("---\ntitle: Limites\nicone: <script>\n---\nTrabalhe só dentro de {{cwd}}. No máximo 5 arquivos.\n")
        self.assertEqual(p.icon, "")  # nome de ícone inválido é descartado
        self.assertEqual(prompts.summary(p, {}), "Trabalhe só dentro de …")
        self.assertEqual(prompts.summary(p, {"cwd": "/a/b"}), "Trabalhe só dentro de /a/b.")
        self.assertNotIn("{{", prompts.summary(p, {}))

    def test_variavel_desconhecida_e_texto_longo(self):
        p = self.load("Rode php artisan {{comando}} " + "e mais " * 60)
        text = prompts.summary(p, {})
        self.assertNotIn("{{", text)
        self.assertLessEqual(len(text), prompts.DESCRIPTION_MAX)
        self.assertTrue(text.startswith("Rode php artisan … e mais"))
