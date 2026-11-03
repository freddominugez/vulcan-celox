"""Regras de arquitetura verificadas por varredura do código-fonte (D4, D5, D7)."""

import ast
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "vulcan_celox"
RUNNER = PKG / "core" / "runner.py"


def _py_files(root):
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


class ArquiteturaTest(unittest.TestCase):
    def test_pacote_existe(self):
        self.assertTrue((PKG / "__init__.py").is_file())
        self.assertTrue((PKG / "__main__.py").is_file())
        self.assertTrue((PKG / "core" / "__init__.py").is_file())
        self.assertTrue((PKG / "ui" / "__init__.py").is_file())

    def test_core_nao_importa_tkinter(self):
        for path in _py_files(PKG / "core"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    self.assertFalse(name.split(".")[0] in ("tkinter", "_tkinter"),
                                     f"{path.relative_to(PKG)} importa {name}")

    def test_sem_apagamento_definitivo(self):
        proibidos = ("shutil.rmtree", "rm -rf", "os.removedirs")
        for path in _py_files(PKG):
            texto = path.read_text(encoding="utf-8")
            for termo in proibidos:
                self.assertNotIn(termo, texto, f"{path.relative_to(PKG)} contém {termo}")

    def test_scripts_sem_apagamento_definitivo(self):
        """A regra vale também para os scripts de desenvolvimento e os de instalação."""
        root = PKG.parent
        for folder in ("scripts", "packaging"):
            for path in sorted((root / folder).rglob("*")):
                if not path.is_file() or path.suffix not in ("", ".sh", ".py"):
                    continue
                texto = path.read_text(encoding="utf-8", errors="replace")
                for termo in ("rm -rf", "rm -fr", "shutil.rmtree"):
                    self.assertNotIn(termo, texto, f"{path.relative_to(root)} contém {termo}")

    def test_shell_true_so_no_runner(self):
        for path in _py_files(PKG):
            if path == RUNNER:
                continue
            self.assertNotIn("shell=True", path.read_text(encoding="utf-8"),
                             f"{path.relative_to(PKG)} usa shell=True")

    def test_subprocess_so_no_runner(self):
        for path in _py_files(PKG):
            if path == RUNNER:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertNotIn("subprocess", [a.name for a in node.names],
                                     f"{path.relative_to(PKG)} importa subprocess")
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(node.module, "subprocess",
                                        f"{path.relative_to(PKG)} importa subprocess")


if __name__ == "__main__":
    unittest.main()
