"""vt-19 C3: todo arquivo em web/vendor tem entrada MIT em LICENSES.md e vem de um pacote conhecido do xterm.js."""

import re
import unittest
from pathlib import Path

VENDOR = Path(__file__).resolve().parent.parent / "vulcan_terminal" / "web" / "vendor"
PACKAGE = {"xterm.js": "@xterm/xterm", "xterm.css": "@xterm/xterm"}


class VendorLicensesTest(unittest.TestCase):
    def test_todo_arquivo_tem_licenca_mit(self):
        text = (VENDOR / "LICENSES.md").read_text(encoding="utf-8")
        headings = dict(re.findall(r"^## (\S+) [0-9.]+ \(([A-Z0-9-]+)\)$", text, re.M))
        for path in sorted(VENDOR.iterdir()):
            if path.name == "LICENSES.md":
                continue
            package = PACKAGE.get(path.name) or f"@xterm/{path.stem}"
            with self.subTest(arquivo=path.name):
                self.assertIn(package, headings, f"{path.name} sem entrada em LICENSES.md")
                self.assertEqual(headings[package], "MIT")

    def test_addons_carregados_pelo_index(self):
        index = (VENDOR.parent / "index.html").read_text(encoding="utf-8")
        for name in ("addon-search", "addon-webgl", "addon-unicode11", "addon-serialize"):
            self.assertIn(f'src="vendor/{name}.js"', index)


if __name__ == "__main__":
    unittest.main()
