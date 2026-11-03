"""Todo arquivo em web/vendor tem entrada MIT em LICENSES.md e vem de um pacote conhecido."""

import json
import re
import unittest
from pathlib import Path

VENDOR = Path(__file__).resolve().parent.parent / "vulcan_celox" / "web" / "vendor"
SCRIPTS = VENDOR.parents[2] / "scripts" / "codemirror"
PACKAGE = {"xterm.js": "@xterm/xterm", "xterm.css": "@xterm/xterm", "codemirror.js": "@codemirror/view", "InterVariable.woff2": "Inter"}
LICENSE_OF = {"Inter": "OFL-1.1"}  # só a fonte tem outra licença; todo o resto precisa ser MIT


class VendorLicensesTest(unittest.TestCase):
    def test_todo_arquivo_tem_licenca_mit(self):
        text = (VENDOR / "LICENSES.md").read_text(encoding="utf-8")
        headings = dict(re.findall(r"^## (\S+) [0-9.]+ \(([A-Z0-9.-]+)\)$", text, re.M))
        for path in sorted(VENDOR.iterdir()):
            if path.name == "LICENSES.md":
                continue
            package = PACKAGE.get(path.name) or f"@xterm/{path.stem}"
            with self.subTest(arquivo=path.name):
                self.assertIn(package, headings, f"{path.name} sem entrada em LICENSES.md")
                self.assertEqual(headings[package], LICENSE_OF.get(package, "MIT"))

    def test_addons_carregados_pelo_index(self):
        index = (VENDOR.parent / "index.html").read_text(encoding="utf-8")
        for name in ("addon-search", "addon-webgl", "addon-unicode11", "addon-serialize"):
            self.assertIn(f'src="vendor/{name}.js"', index)


class FonteTest(unittest.TestCase):
    def test_woff2_de_verdade(self):
        self.assertEqual((VENDOR / "InterVariable.woff2").read_bytes()[:4], b"wOF2")

    def test_licenca_da_fonte_na_integra(self):
        self.assertIn("SIL Open Font License, Version 1.1", (VENDOR / "LICENSES.md").read_text(encoding="utf-8"))

    def test_carregada_sem_recurso_externo(self):
        tokens = (VENDOR.parent / "styles" / "tokens.css").read_text(encoding="utf-8")
        self.assertIn('url("../vendor/InterVariable.woff2")', tokens)
        self.assertIn("font-weight: 100 900", tokens)


class CodemirrorVendorTest(unittest.TestCase):
    def setUp(self):
        self.bundle = (VENDOR / "codemirror.js").read_bytes()
        self.licenses = (VENDOR / "LICENSES.md").read_text(encoding="utf-8")

    def test_tamanho_e_sem_eval(self):
        self.assertLessEqual(len(self.bundle), 800 * 1024)
        self.assertNotRegex(self.bundle, rb"\beval\(|new Function")
        self.assertTrue(self.bundle.startswith(b"/* CodeMirror 6"), "gerado em IIFE, sem build no app")

    def test_nao_carrega_na_abertura_do_app(self):
        # 767 KB só entram quando a aba Código abre
        index = (VENDOR.parent / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("codemirror", index)

    def test_versoes_fixas_e_lockfile_coerentes(self):
        pkg = json.loads((SCRIPTS / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((SCRIPTS / "package-lock.json").read_text(encoding="utf-8"))["packages"]
        for group in ("dependencies", "devDependencies"):
            for name, version in pkg[group].items():
                with self.subTest(pacote=name):
                    self.assertRegex(version, r"^\d+\.\d+\.\d+$", "versão sem faixa")
                    self.assertEqual(lock[f"node_modules/{name}"]["version"], version)

    def test_toda_dependencia_direta_tem_licenca_listada_com_a_versao_do_lock(self):
        lock = json.loads((SCRIPTS / "package-lock.json").read_text(encoding="utf-8"))["packages"]
        marca = self.licenses.index("<!-- codemirror:")
        listed = dict(re.findall(r"^## (\S+) ([0-9.]+) \(MIT\)$", self.licenses[marca:], re.M))
        self.assertGreaterEqual(len(listed), 30)
        for name, version in listed.items():
            with self.subTest(pacote=name):
                self.assertEqual(lock[f"node_modules/{name}"]["version"], version)
                self.assertEqual(lock[f"node_modules/{name}"].get("license"), "MIT")
        for name in json.loads((SCRIPTS / "package.json").read_text(encoding="utf-8"))["dependencies"]:
            self.assertIn(name, listed)
        self.assertNotIn("esbuild", listed, "ferramenta de geração não entra no app")


if __name__ == "__main__":
    unittest.main()
