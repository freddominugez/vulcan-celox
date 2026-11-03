"""Os seis ajustes comuns do php.ini de usuário do Lerd.

A gravação passa pelo próprio `lerd php:ini [versão|shared]` com EDITOR apontando para este módulo: o Lerd entrega o
caminho do arquivo ao "editor" e reaplica o PHP-FPM quando ele termina, como faz ao salvar no nano ou no vim.
Este módulo, rodado como editor, faz uma cópia `.bak-<data>` ao lado e altera só as linhas das chaves pedidas.
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
    """Valores das seis chaves que estão valendo (linhas sem ponto e vírgula)."""
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
    """Troca a linha da chave; sem ela, acrescenta no fim; com None, tira a linha. O resto fica igual."""
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
    """Aplica as mudanças com cópia ao lado; devolve o caminho da cópia."""
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
    """Usado como EDITOR pelo `lerd php:ini`: recebe o caminho e lê as mudanças de VULCAN_PHP_INI_SET."""
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
