"""Processo e dados locais."""

import os
import shutil
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path

from tests.helpers import TempDirTestCase
from vulcan_terminal.core.agents.index import AgentIndex
from vulcan_terminal.core.doc_prompts import session_doc_prompt
from vulcan_terminal.core.sessions import SessionRecord
from vulcan_terminal.core.store import Store, secure_data_dir, write_text_atomic
from vulcan_terminal.desktop_linux import app_window_argv, write_launcher

ROOT = Path(__file__).resolve().parent.parent
TOKEN = "t" * 43


def mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


class LancadorLinuxTest(TempDirTestCase):
    def test_token_fora_da_linha_de_comando(self):
        launcher = write_launcher(self.tmp / "dados", 5000, TOKEN, "#/overview")
        self.assertEqual(mode(launcher), 0o600)
        self.assertIn(TOKEN, launcher.read_text(encoding="utf-8"))
        argv = app_window_argv("/usr/bin/chromium", launcher, self.tmp / "perfil")
        self.assertFalse(any(TOKEN in a for a in argv), argv)
        self.assertIn(f"--app={launcher.as_uri()}", argv)

    def test_lancador_regravado_continua_privado(self):
        first = write_launcher(self.tmp / "dados", 5000, TOKEN, "#/overview")
        os.chmod(first, 0o644)
        second = write_launcher(self.tmp / "dados", 5001, "u" * 43, "#/overview")
        self.assertEqual(second, first)
        self.assertEqual(mode(second), 0o600)
        self.assertNotIn(TOKEN, second.read_text(encoding="utf-8"))


class PermissoesTest(TempDirTestCase):
    def test_pasta_de_dados_privada(self):
        data = self.tmp / "dados"
        (data / "sessoes" / "loja").mkdir(parents=True)
        antigo = data / "sessoes" / "loja" / "memoria.md"
        antigo.write_text("x")
        os.chmod(antigo, 0o644)
        os.chmod(data, 0o755)
        secure_data_dir(data)
        self.assertEqual(mode(data), 0o700)
        self.assertEqual(mode(data / "sessoes"), 0o700)
        self.assertEqual(mode(antigo), 0o600)
        Store(data).save("tasks", [])
        self.assertEqual(mode(data / "tasks.json"), 0o600)
        write_text_atomic(data / "sessoes" / "loja" / "nova.md", "y")
        self.assertEqual(mode(data / "sessoes" / "loja" / "nova.md"), 0o600)

    def test_script_executavel_continua_executavel(self):
        # o hook de pareamento e o ajudante do php.ini são executados direto
        data = self.tmp / "dados"
        (data / "hooks").mkdir(parents=True)
        script = data / "hooks" / "vulcan-pareamento.py"
        script.write_text("#!/usr/bin/env python3\n")
        os.chmod(script, 0o755)
        secure_data_dir(data)
        self.assertEqual(mode(script), 0o700)

    def test_pasta_de_projeto_continua_legivel(self):
        secure_data_dir(self.tmp / "dados")
        projeto = self.tmp / "projeto"
        write_text_atomic(projeto / "TAREFAS.md", "z")
        self.assertEqual(mode(projeto / "TAREFAS.md"), 0o644)

    def test_symlink_na_pasta_de_dados_nao_e_seguido(self):
        data = self.tmp / "dados"
        data.mkdir()
        fora = self.tmp / "fora.txt"
        fora.write_text("x")
        os.chmod(fora, 0o644)
        os.symlink(fora, data / "link.txt")
        secure_data_dir(data)
        self.assertEqual(mode(fora), 0o644)

    def test_indice_em_wal_e_privado(self):
        data = self.tmp / "dados"
        secure_data_dir(data)
        index = AgentIndex(data / "agentes.db")
        try:
            self.assertEqual(index.db.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
            self.assertEqual(mode(data / "agentes.db"), 0o600)
            other = sqlite3.connect(str(data / "agentes.db"), timeout=1)  # leitor de fora (ex.: --doctor)
            with index.lock:
                index.db.execute("BEGIN IMMEDIATE")
                index.db.execute("UPDATE meta SET value = value WHERE key = 'revision'")
                self.assertTrue(other.execute("SELECT value FROM meta WHERE key = 'revision'").fetchone())
                index.db.commit()
            other.close()
        finally:
            index.close()


class MascaraAntesDoCorteTest(TempDirTestCase):
    def test_segredo_na_fronteira_do_corte(self):
        secret = "sk-ant-api03-" + "A" * 40
        prefix = "export KEY= " + "x" * 100 + " "
        transcript = prefix + secret + " " + "y" * 50
        limit = len(transcript) - len(prefix) - 3  # o corte cai depois de "sk-": sobraria "ant-api03-AAA..."
        record = SessionRecord(id="aba1", title="loja", cwd="/r/loja", created_at="2026-10-31T10:00:00Z")
        prompt = session_doc_prompt(record, [], [], {}, transcript, limit=limit)
        self.assertNotIn("A" * 40, prompt.user)
        self.assertGreaterEqual(prompt.redactions, 1)


class PastaDeTrabalhoTest(TempDirTestCase):
    def test_modulo_hostil_na_pasta_atual_nao_e_importado(self):
        if not shutil.which("sh"):
            self.skipTest("sem sh")
        hostil = self.tmp / "repo-clonado"
        hostil.mkdir()
        marker = self.tmp / "importou"
        (hostil / "secrets.py").write_text(f"open({str(marker)!r}, 'w').write('x')\nraise SystemExit(9)\n")
        bin_dir, lib = self.tmp / "inst" / "bin", self.tmp / "inst" / "lib"
        bin_dir.mkdir(parents=True)
        lib.mkdir()
        os.symlink(ROOT / "vulcan_terminal", lib / "vulcan_terminal")
        shutil.copy(ROOT / "packaging" / "linux" / "vulcan-terminal", bin_dir / "vulcan-terminal")
        env = {"PATH": os.environ.get("PATH", ""), "VULCAN_PYTHON": sys.executable,
               "HOME": str(self.tmp), "VULCAN_TERMINAL_HOME": str(self.tmp / "h")}
        proc = subprocess.run(["sh", str(bin_dir / "vulcan-terminal"), "--version"], cwd=str(hostil), env=env,
                              capture_output=True, text=True, timeout=60)
        self.assertFalse(marker.exists(), "o lançador importou secrets.py da pasta atual")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Vulcan Terminal", proc.stdout)
