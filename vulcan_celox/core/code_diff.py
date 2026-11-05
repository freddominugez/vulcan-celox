"""Diff against git without letting the repository run anything: the HEAD content comes from `cat-file blob`, which does not go
through diff.external, textconv or filters, and the current file is read directly. The analyzed repository is third-party."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from vulcan_celox.core import code_files
from vulcan_celox.core.agents.repos import SAFE_GIT
from vulcan_celox.core.runner import capture

MAX_OUTPUT = 2 * 1024 * 1024
GIT_SECONDS = 10.0


def _capture(argv, limit: int) -> Tuple[Optional[int], bytes]:
    """(exit code or None if git did not run, up to limit + 1 bytes of output). Never keeps more than that."""
    code, raw, timed_out = capture(argv, limit, GIT_SECONDS)
    return (1 if timed_out and code is not None else code), raw


def _toplevel(folder: str) -> Tuple[Optional[str], str]:
    """(repository root, reason if there is none)."""
    code, raw = _capture([*SAFE_GIT, "-C", folder, "rev-parse", "--show-toplevel"], 8192)
    if code is None:
        return None, "no_git"
    if code != 0 or not raw.strip():
        return None, "no_repo"
    return raw.decode("utf-8", "surrogateescape").rstrip("\n"), ""


def _head_blob(toplevel: str, rel: str) -> Tuple[Optional[bytes], bool]:
    """(content at HEAD or None if it does not exist there, truncated?)."""
    code, raw = _capture([*SAFE_GIT, "-C", toplevel, "cat-file", "blob", f"HEAD:{rel}"], MAX_OUTPUT)
    if len(raw) > MAX_OUTPUT:
        return raw[:MAX_OUTPUT], True
    return (raw, False) if code == 0 else (None, False)


def git_sides(real: Path) -> Dict[str, Any]:
    """Sides of a file's diff against HEAD. `real` has already passed the root and sensitive-name check."""
    folder = real.parent
    while not folder.is_dir() and folder != folder.parent:
        folder = folder.parent  # the file may have been deleted along with the folder
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
    old, new = "" if raw is None else raw.decode("utf-8", "replace"), current["text"]
    if os.name == "nt" and raw is not None:
        # with core.autocrlf (Git default on Windows), HEAD stores \n and the working tree \r\n: without this, every line changes
        old, new = old.replace("\r\n", "\n"), new.replace("\r\n", "\n")
    return {"available": True, "status": "new" if raw is None else "modified", "old": old, "new": new,
            "complete": not truncated, "truncated": truncated}
