"""Vulcan Celox shell on Windows: the same as on Linux, in Edge or Chrome app window mode."""

from __future__ import annotations

import sys

from vulcan_celox.desktop_linux import main

if __name__ == "__main__":
    sys.exit(main())
