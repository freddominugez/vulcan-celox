"""Pool identity and liveness with delayed and unavailable snapshots."""

import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("node"), "sem node")
class TerminalPoolTest(unittest.TestCase):
    def test_reconciliacao(self):
        script = Path(__file__).with_name("tools") / "terminal_pool.mjs"
        run = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
