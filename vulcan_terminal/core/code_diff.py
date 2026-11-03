"""Diff contra o git sem deixar o repositório executar nada: o conteúdo de HEAD sai por `cat-file blob`, que não passa
por diff.external, textconv nem filtros, e o arquivo atual é lido direto. O repositório analisado é de terceiros."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from vulcan_terminal.core import code_files
from vulcan_terminal.core.agents.repos import SAFE_GIT
from vulcan_terminal.core.runner import close_pipe, open_pipe

MAX_OUTPUT = 2 * 1024 * 1024


def _capture(argv, limit: int) -> Tuple[Optional[int], bytes]:
    """(código de saída ou None se o git não rodou, até limit + 1 bytes da saída). Nunca guarda mais que isso."""
    try:
        proc = open_pipe(argv)
    except OSError:
        return None, b""
    raw = proc.stdout.read(limit + 1)
    return close_pipe(proc), raw


def _toplevel(folder: str) -> Tuple[Optional[str], str]:
    """(raiz do repositório, motivo se não houver)."""
    code, raw = _capture([*SAFE_GIT, "-C", folder, "rev-parse", "--show-toplevel"], 8192)
    if code is None:
        return None, "no_git"
    if code != 0 or not raw.strip():
        return None, "no_repo"
    return raw.decode("utf-8", "surrogateescape").rstrip("\n"), ""


def _head_blob(toplevel: str, rel: str) -> Tuple[Optional[bytes], bool]:
    """(conteúdo em HEAD ou None se não existe lá, cortado?)."""
    code, raw = _capture([*SAFE_GIT, "-C", toplevel, "cat-file", "blob", f"HEAD:{rel}"], MAX_OUTPUT)
    if len(raw) > MAX_OUTPUT:
        return raw[:MAX_OUTPUT], True
    return (raw, False) if code == 0 else (None, False)


def git_sides(real: Path) -> Dict[str, Any]:
    """Lados do diff de um arquivo contra HEAD. `real` já passou pela checagem de raiz e de nome sensível."""
    folder = real.parent
    while not folder.is_dir() and folder != folder.parent:
        folder = folder.parent  # o arquivo pode ter sido apagado junto com a pasta
    toplevel, reason = _toplevel(str(folder))
    if toplevel is None:
        return {"available": False, "reason": reason}
    try:
        rel = real.relative_to(Path(toplevel).resolve()).as_posix()
    except ValueError:
        return {"available": False, "reason": "no_repo"}
    raw, truncated = _head_blob(toplevel, rel)
    if raw is not None and b"\x00" in raw:
        return {"available": False, "reason": "binary"}
    try:
        current = code_files.read_for_viewer(str(real), [toplevel])
    except code_files.CodeReadError as err:
        if err.reason != "missing":
            return {"available": False, "reason": err.reason}
        if raw is None:
            return {"available": False, "reason": "missing"}
        return {"available": True, "status": "deleted", "old": raw.decode("utf-8", "replace"), "new": "",
                "complete": not truncated, "truncated": truncated}
    return {"available": True, "status": "new" if raw is None else "modified",
            "old": "" if raw is None else raw.decode("utf-8", "replace"), "new": current["text"],
            "complete": not truncated, "truncated": truncated}
