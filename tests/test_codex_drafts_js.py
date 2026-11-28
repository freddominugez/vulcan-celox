"""Codex drafts use literal Unicode and move only when a destination is explicitly chosen."""

import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("node"), "sem node")
class CodexDraftsTest(unittest.TestCase):
    def test_validacao_e_identidade(self):
        script = Path(__file__).with_name("tools") / "codex_drafts.mjs"
        run = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
