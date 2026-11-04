"""Vulcan Celox test suite.

Watchdog: if the suite runs past 15 min (normal: about 2 min), it dumps the stack of every thread and exits with an error,
so validate.sh fails with the cause instead of hanging. One run hung once on 2026-10-31
and did not repeat in five consecutive runs; if it comes back, the stack shows where.
"""

import faulthandler
import sys

faulthandler.dump_traceback_later(900, repeat=False, file=sys.stderr, exit=True)

import os  # noqa: E402

# the suite checks the source text, including in subprocesses; English has its own test (tests/test_i18n.py)
os.environ["VULCAN_LANGUAGE"] = "pt"

from vulcan_celox.core import i18n  # noqa: E402

i18n.DEFAULT = "pt"
i18n.set_language("pt")
