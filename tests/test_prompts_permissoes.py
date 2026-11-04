"""Prompts and categories in the app data folder are written as 0600 and 0700; in the project
folder they stay as the editor would create them."""
import os
import stat

from tests.helpers import TempDirTestCase, unix_only, MODOS
from vulcan_celox.core import prompts
from vulcan_celox.core.store import secure_data_dir


def mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


class PromptsPermissoesTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.old_umask = os.umask(0o022)
        self.addCleanup(os.umask, self.old_umask)
        self.data = secure_data_dir(self.tmp / "dados")

    @unix_only(MODOS)
    def test_exemplos_criados_depois_de_proteger_a_pasta(self):
        created = prompts.seed_global(self.data / "prompts")
        self.assertTrue(created)
        self.assertEqual(mode(self.data / "prompts"), 0o700)
        for path in created:
            self.assertEqual(mode(path), 0o600, path)
            self.assertEqual(mode(path.parent), 0o700, path.parent)

    @unix_only(MODOS)
    def test_prompt_e_categoria_novos_na_pasta_global(self):
        root = self.data / "prompts"
        path = prompts.create_prompt(root, "Deploy", "Minha Categoria")
        self.assertEqual(mode(path), 0o600)
        self.assertEqual(mode(path.parent), 0o700)
        self.assertEqual(mode(path.parent / prompts.NAME_FILE), 0o600)
        folder = prompts.create_category(root, "Outra")
        self.assertEqual(mode(folder), 0o700)

    @unix_only(MODOS)
    def test_pasta_do_projeto_continua_como_o_editor_criaria(self):
        project = self.tmp / "projeto"
        project.mkdir()
        path = prompts.create_prompt(prompts.project_dir(str(project)), "Deploy", "Publicação")
        self.assertEqual(mode(path), 0o644)
        self.assertEqual(mode(path.parent), 0o755)
