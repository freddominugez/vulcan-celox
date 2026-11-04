"""The six common settings of the user php.ini in Lerd.

Writing goes through `lerd php:ini [version|shared]` itself with EDITOR pointing at this module: Lerd hands the
file path to the "editor" and reapplies PHP-FPM when it finishes, as it does when saving in nano or vim.
This module, run as an editor, makes a `.bak-<date>` copy alongside and changes only the lines of the requested keys.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from typing import Dict, Optional

KEYS = ("memory_limit", "upload_max_filesize", "post_max_size", "max_execution_time", "display_errors",
        "error_reporting")
VALUE = re.compile(r"^[A-Za-z0-9_.&~| -]{1,60}$")  # 512M, 60, On, E_ALL & ~E_DEPRECATED
ENV_CHANGES = "VULCAN_PHP_INI_SET"


def _line(key: str) -> re.Pattern:
    return re.compile(rf"^\s*{re.escape(key)}\s*=")


def check(key: str, value: Optional[str]) -> None:
    if key not in KEYS:
        raise ValueError(f"chave fora das seis comuns: {key}")
    if value is not None and not VALUE.match(str(value)):
        raise ValueError(f"valor inválido para {key}: {value!r}")


def parse_directives(text: str) -> Dict[str, str]:
    """Values of the six keys currently in effect (lines without a semicolon)."""
    out: Dict[str, str] = {}
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        key, sep, value = stripped.partition("=")
        if sep and key.strip() in KEYS:
            out[key.strip()] = value.strip().strip('"')
    return out


def set_directive(text: str, key: str, value: Optional[str]) -> str:
    """Replaces the key's line; without it, appends at the end; with None, removes the line. The rest stays the same."""
    check(key, value)
    lines = (text or "").splitlines()
    pattern = _line(key)
    found = [i for i, line in enumerate(lines) if pattern.match(line)]
    if value is None:
        lines = [line for i, line in enumerate(lines) if i not in found]
    elif found:
        lines[found[0]] = f"{key} = {value}"
        lines = [line for i, line in enumerate(lines) if i not in found[1:]]
    else:
        lines.append(f"{key} = {value}")
    return "\n".join(lines) + "\n"


def edit_file(path: str, changes: Dict[str, Optional[str]]) -> str:
    """Applies the changes with a copy alongside; returns the copy's path."""
    for key, value in changes.items():
        check(key, value)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    backup = f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, backup)
    for key, value in changes.items():
        text = set_directive(text, key, value)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return backup


def main(argv=None) -> int:
    """Used as EDITOR by `lerd php:ini`: receives the path and reads the changes from VULCAN_PHP_INI_SET."""
    args = sys.argv[1:] if argv is None else argv
    if not args:
        return 2
    try:
        changes = json.loads(os.environ.get(ENV_CHANGES) or "{}")
        if not isinstance(changes, dict) or not changes:
            return 2
        edit_file(args[-1], changes)
    except (OSError, ValueError) as err:
        print(f"php.ini não alterado: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
