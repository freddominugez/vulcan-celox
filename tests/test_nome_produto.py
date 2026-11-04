"""The product is Vulcan Celox everywhere, including in technical names. Only the migration cites the old names."""

import re
import subprocess
import sys
import unittest
from pathlib import Path

from vulcan_celox import APP_NAME, __version__
from vulcan_celox.core import keychain

ROOT = Path(__file__).resolve().parent.parent
PACOTE = ROOT / "vulcan_celox"
OLD_NAMES = re.compile("Vulcan " + "Terminal|vulcan" + "_terminal|vulcan-" + "terminal|Vulcan" + "Terminal|VULCAN_" + "TERMINAL|com\\.byvulcan\\." + "terminal")
# migration and the install notice need to cite the old name
PODE_CITAR = {"core/oscompat.py", "core/keychain.py"}


class NomeTest(unittest.TestCase):
    def test_app_name(self):
        self.assertEqual(APP_NAME, "Vulcan Celox")

    def test_codigo_sem_nome_antigo(self):
        hits = []
        for path in PACOTE.rglob("*"):
            if not path.is_file() or path.suffix not in (".py", ".mjs", ".js", ".css", ".html", ".json") or "vendor" in path.parts:
                continue
            rel = path.relative_to(PACOTE).as_posix()
            if rel not in PODE_CITAR and OLD_NAMES.search(path.read_text(encoding="utf-8")):
                hits.append(rel)
        self.assertEqual(hits, [])

    def test_casca_e_empacotamento(self):
        paths = [ROOT / "packaging" / "macos" / "main.swift", ROOT / "packaging" / "macos" / "notify.swift", ROOT / "scripts" / "build_app.sh", ROOT / "scripts" / "package.sh",
                 ROOT / "packaging" / "linux" / "vulcan-celox.desktop", ROOT / "packaging" / "linux" / "install.sh"]
        for path in paths:
            with self.subTest(arquivo=path.name):
                self.assertIsNone(OLD_NAMES.search(path.read_text(encoding="utf-8")))

    def test_bundle(self):
        build = (ROOT / "scripts" / "build_app.sh").read_text(encoding="utf-8")
        self.assertIn('APP="dist/Vulcan Celox.app"', build)
        self.assertIn("com.byvulcan.celox", build)

    def test_keychain_novo(self):
        self.assertEqual(keychain.SERVICE, "com.byvulcan.celox.anthropic")

    def test_version(self):
        out = subprocess.run([sys.executable, "-m", "vulcan_celox", "--version"], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertIn(f"{APP_NAME} {__version__}", out.stdout + out.stderr)
