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


def is_windows(system: Optional[str] = None) -> bool:
    return (system or sys.platform) == "win32"


def default_shell(env: Optional[Mapping[str, str]] = None, exists=os.path.exists) -> str:
    """$SHELL se existir; senão o primeiro entre zsh, bash e sh. No Windows, PowerShell e por último o cmd."""
    env = os.environ if env is None else env
    if is_windows():
        return shutil.which("pwsh.exe") or shutil.which("powershell.exe") or env.get("COMSPEC") or "cmd.exe"
    shell = env.get("SHELL")
    if shell and exists(shell):
        return shell
    return next((s for s in SHELL_CANDIDATES if exists(s)), "/bin/sh")


def _shell_name(shell: str) -> str:
    return shell.replace("\\", "/").rsplit("/", 1)[-1].lower()


def shell_command_argv(shell: str, command: str) -> List[str]:
    """Roda um comando e sai."""
    name = _shell_name(shell)
    if name.startswith(("powershell", "pwsh")):
        return [shell, "-NoLogo", "-NoProfile", "-Command", command]
    if name.startswith("cmd"):
        return [shell, "/c", command]
    return [shell, "-lc", command]


def interactive_argv(shell: str, command: Optional[str]) -> List[str]:
    """Shell interativo; com comando, roda ele e continua no shell, como no Terminal."""
    name = _shell_name(shell)
    if name.startswith(("powershell", "pwsh")):
        return [shell, "-NoLogo"] + (["-NoExit", "-Command", command] if command else [])
    if name.startswith("cmd"):
        return [shell] + (["/k", command] if command else [])
    if not command:
        return [shell, "-l"]
    return [shell, "-l", "-i", "-c", f"{command}; exec {shell} -l"]


# nome da pasta até a 1.1: quem já usa o app tem os dados lá
OLD_MACOS_FOLDER = "VulcanTerminal"
OLD_LINUX_FOLDER = "vulcan-" + "terminal"


def _folders(env: Mapping[str, str], system: Optional[str]) -> Tuple[Path, Path]:
    """(pasta de dados, pasta com o nome antigo)."""
    home = Path(env.get("HOME") or Path.home())
    if is_windows(system):
        folder = Path(env.get("APPDATA") or home / "AppData" / "Roaming") / "VulcanCelox"
        return folder, folder  # o nome antigo nunca existiu no Windows: não há o que migrar
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


def _windows_open_argv(kind: str, target: str, editor: Optional[str], which) -> List[str]:
    """Sem passar por cmd.exe nem por .cmd: & num nome de arquivo viraria um segundo comando."""
    if kind == "url":
        return ["rundll32.exe", "url.dll,FileProtocolHandler", target]
    if kind != "editor":
        return ["explorer.exe", target]
    if editor:
        return [editor, target]
    code = which("code")
    if code and code.lower().endswith(".cmd"):  # o VS Code instala bin\\code.cmd ao lado de ..\\Code.exe
        exe = os.path.join(os.path.dirname(os.path.dirname(code)), "Code.exe")
        if os.path.exists(exe):
            return [exe, target]
    return ["explorer.exe", target] if os.path.isdir(target) else ["notepad.exe", target]


def open_argv(kind: str, target: str, env: Optional[Mapping[str, str]] = None, system: Optional[str] = None,
              which=shutil.which) -> List[str]:
    """Comando para abrir URL, pasta, arquivo ou pasta no editor."""
    env = os.environ if env is None else env
    editor = env.get("VULCAN_EDITOR")
    if is_windows(system):
        return _windows_open_argv(kind, target, editor, which)
    if is_macos(system):
        if kind == "editor":
            return ["/usr/bin/open", "-a", editor, target] if editor else ["/usr/bin/open", "-t", target]
        return ["/usr/bin/open", target]
    if kind == "editor":
        chosen = editor or next((e for e in ("code", "codium", "subl", "gnome-text-editor", "kate") if which(e)), None)
        if chosen:
            return [which(chosen) or chosen, target]
    return [which("xdg-open") or "xdg-open", target]
