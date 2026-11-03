"""Nada é apagado de forma definitiva: arquivos vão para a Lixeira do sistema ou, se não der, para `lixeira/`
dentro da pasta de dados do Vulcan Celox."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Optional

from vulcan_celox.core.oscompat import is_macos

TRASH_DIR = "lixeira"


def _applescript_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def move_to_trash(path, data_dir, runner, system: Optional[str] = None) -> Path:
    """Move `path` para a Lixeira e devolve onde ficou (o próprio caminho original se foi para a Lixeira do sistema)."""
    path = Path(path)
    if not path.exists():
        return path
    if is_macos(system):
        script = f"tell application \"Finder\" to delete POSIX file {_applescript_string(str(path))}"
        runner.run(["/usr/bin/osascript", "-e", script], timeout=20)
    else:
        gio = shutil.which("gio")
        if gio:
            runner.run([gio, "trash", str(path)], timeout=20)
    if not path.exists():
        return path
    # sem Lixeira disponível: guarda na pasta de dados, com data para não sobrescrever
    target_dir = Path(data_dir) / TRASH_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{path.name}"
    shutil.move(str(path), str(target))
    return target
