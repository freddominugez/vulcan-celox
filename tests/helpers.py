"""Test utilities: isolated temporary directories."""

import re
import sys
import tempfile
import time
import unittest
from pathlib import Path

WINDOWS = sys.platform == "win32"
SEM_LERD = "Lerd e Valet não existem no Windows, e o executável falso é um script de shell Unix"
MODOS = "modos de arquivo Unix não têm efeito no Windows"
_ANSI = re.compile(rb"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07]*\x07)")


def unix_only(reason):
    """Skips on Windows, with the reason written in the suite report."""
    return unittest.skipIf(WINDOWS, reason)


def py_argv(code):
    """Test process that exists on every system, without depending on a shell."""
    return [sys.executable, "-c", code]


def strip_ansi(data: bytes) -> bytes:
    """Terminal output without the control sequences: PowerShell colors what is typed."""
    return _ANSI.sub(b"", data)


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="vulcan-test-")
        self.tmp = Path(self._tmp.name)
        # last: whatever the test registers with addCleanup (closing index, tab) runs before the folder is deleted,
        # because on Windows a folder with an open file cannot be deleted
        self.addCleanup(self._remove_tmp)

    def _remove_tmp(self):
        for _ in range(25 if WINDOWS else 0):  # a just-terminated process still holds the folder for a moment
            try:
                self._tmp.cleanup()
                return
            except OSError:
                time.sleep(0.2)
        self._tmp.cleanup()


FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOLDEN = Path(__file__).resolve().parent / "golden"
