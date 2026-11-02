"""Diferenças entre macOS e Linux concentradas num lugar: shell padrão, pasta de dados e como abrir coisas."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import List, Mapping, Optional

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


def default_data_dir(env: Optional[Mapping[str, str]] = None, system: Optional[str] = None) -> Path:
    env = os.environ if env is None else env
    home = Path(env.get("HOME") or Path.home())
    if is_macos(system):
        return home / "Library" / "Application Support" / "VulcanTerminal"
    base = env.get("XDG_DATA_HOME")
    return (Path(base) if base else home / ".local" / "share") / "vulcan-terminal"


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
