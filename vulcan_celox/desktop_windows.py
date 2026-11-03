"""Casca do Vulcan Celox no Windows: a mesma do Linux, em modo janela de app do Edge ou Chrome."""

from __future__ import annotations

import sys

from vulcan_celox.desktop_linux import main

if __name__ == "__main__":
    sys.exit(main())
