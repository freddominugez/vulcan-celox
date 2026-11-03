"""Diferenças entre macOS e Linux concentradas num lugar: shell padrão, pasta de dados e como abrir coisas."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Tuple, List, Mapping, Optional

SHELL_CANDIDATES = ("/bin/zsh", "/usr/bin/zsh", "/bin/bash", "/usr/bin/bash", "/bin/sh")


def is_macos(system: Optional[str] = None) -> bool:
    return (system or sys.platform) == "darwin"


def default_shell(env: Optional[Mapping[str, str]] = None, exists=os.path.exists) -> str:
    """$SHELL se existir; senão o primeiro entre zsh, bash e sh."""
    env = os.environ if env is None else env
    shell = env.get("SHELL")
    if shell and exists(shell):
        return shell
    return next((s for s in SHELL_CANDIDATES if exists(s)), "/bin/sh")


# nome da pasta até a 1.1: quem já usa o app tem os dados lá
OLD_MACOS_FOLDER = "VulcanTerminal"
OLD_LINUX_FOLDER = "vulcan-" + "terminal"


def _folders(env: Mapping[str, str], system: Optional[str]) -> Tuple[Path, Path]:
    """(pasta de dados, pasta com o nome antigo)."""
    home = Path(env.get("HOME") or Path.home())
    if is_macos(system):
        support = home / "Library" / "Application Support"
        return support / "VulcanCelox", support / OLD_MACOS_FOLDER
    base = env.get("XDG_DATA_HOME")
    root = Path(base) if base else home / ".local" / "share"
    return root / "vulcan-celox", root / OLD_LINUX_FOLDER


def migrate_old_folder(env: Optional[Mapping[str, str]] = None, system: Optional[str] = None) -> None:
    """Primeira abertura depois do novo nome: a pasta muda de nome inteira e fica um link no lugar antigo, porque o hook
    já instalado no agente aponta para lá. Com as duas pastas, ou sem permissão, não mexe em nada. Só o início do app chama
    isto: calcular o caminho nunca move nada."""
    new, old = _folders(os.environ if env is None else env, system)
    try:
        if old.is_dir() and not old.is_symlink() and not new.exists():
            new.parent.mkdir(parents=True, exist_ok=True)
            os.rename(old, new)
            os.symlink(new, old)
    except OSError:
        pass


def default_data_dir(env: Optional[Mapping[str, str]] = None, system: Optional[str] = None) -> Path:
    return _folders(os.environ if env is None else env, system)[0]


def open_argv(kind: str, target: str, env: Optional[Mapping[str, str]] = None, system: Optional[str] = None,
              which=shutil.which) -> List[str]:
    """Comando para abrir URL, pasta, arquivo ou pasta no editor."""
    env = os.environ if env is None else env
    editor = env.get("VULCAN_EDITOR")
    if is_macos(system):
        if kind == "editor":
            return ["/usr/bin/open", "-a", editor, target] if editor else ["/usr/bin/open", "-t", target]
        return ["/usr/bin/open", target]
    if kind == "editor":
        chosen = editor or next((e for e in ("code", "codium", "subl", "gnome-text-editor", "kate") if which(e)), None)
        if chosen:
            return [which(chosen) or chosen, target]
    return [which("xdg-open") or "xdg-open", target]
