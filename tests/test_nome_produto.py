"""O produto se apresenta como Vulcan Celox, sem mexer em onde estão os dados de quem já usa (decisão sobre o nome)."""

import re
import subprocess
import sys
import unittest
from pathlib import Path

from vulcan_terminal import APP_NAME, __version__
from vulcan_terminal.core import oscompat

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "vulcan_terminal" / "web"
OLD = "Vulcan Terminal"
# o que o usuário vê: interface, casca, empacotamento e texto gravado em arquivo
VISIBLE = [WEB / "index.html", WEB / "help" / "conteudo.json", ROOT / "packaging" / "macos" / "main.swift", ROOT / "docs" / "pt-BR" / "user-guide.md",
           ROOT / "scripts" / "build_app.sh", ROOT / "scripts" / "package.sh",
           ROOT / "packaging" / "linux" / "vulcan-terminal.desktop",
           *WEB.glob("js/**/*.mjs"), *WEB.glob("styles/*.css"), *(ROOT / "vulcan_terminal" / "core").rglob("*.py"),
           *(ROOT / "vulcan_terminal" / "server").rglob("*.py")]


class NomeVisivelTest(unittest.TestCase):
    def test_app_name(self):
        self.assertEqual(APP_NAME, "Vulcan Celox")

    def test_textos_sem_o_nome_antigo(self):
        hits = [str(p.relative_to(ROOT)) for p in VISIBLE if OLD in p.read_text(encoding="utf-8")]
        self.assertEqual(hits, [])

    def test_bundle_com_nome_novo(self):
        build = (ROOT / "scripts" / "build_app.sh").read_text(encoding="utf-8")
        self.assertIn('APP="dist/Vulcan Celox.app"', build)
        self.assertEqual(len(re.findall(r"<string>Vulcan Celox</string>", build)), 2)

    def test_version(self):
        out = subprocess.run([sys.executable, "-m", "vulcan_terminal", "--version"], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertIn(APP_NAME, out.stdout + out.stderr)
        self.assertIn(__version__, out.stdout + out.stderr)


class DadosNoMesmoLugarTest(unittest.TestCase):
    def test_pasta_de_dados_nao_muda(self):
        source = (ROOT / "vulcan_terminal" / "core" / "oscompat.py").read_text(encoding="utf-8")
        self.assertIn('"VulcanTerminal"', source)
        self.assertIn("vulcan-terminal", source)
        self.assertTrue(oscompat)

    def test_identificador_do_app_nao_muda(self):
        self.assertIn("com.byvulcan.terminal", (ROOT / "scripts" / "build_app.sh").read_text(encoding="utf-8"))

    def test_servico_do_keychain_nao_muda(self):
        self.assertIn("com.byvulcan.terminal", (ROOT / "vulcan_terminal" / "core" / "keychain.py").read_text(encoding="utf-8"))

    def test_tamanho_da_janela_continua_lembrado(self):
        self.assertIn('setFrameAutosaveName("VulcanTerminalMain")', (ROOT / "packaging" / "macos" / "main.swift").read_text(encoding="utf-8"))
