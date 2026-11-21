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


def _head_blob(toplevel: str, base: str, rel: str) -> Tuple[Optional[bytes], bool, bool]:
    """Return the old bytes, truncation, and whether the path is demonstrably absent."""
    argv = [*SAFE_GIT, "-C", toplevel]
    code, raw = _capture([*argv, "cat-file", "blob", f"{base}:{rel}"], MAX_OUTPUT)
    if len(raw) > MAX_OUTPUT:
        return raw[:MAX_OUTPUT], True, False
    if code == 0:
        return raw, False, False
    code, entries = _capture([*argv, "ls-tree", "-z", "--full-tree", base, "--", f":(literal){rel}"], 8192)
    return None, False, code == 0 and not entries


def git_sides(real: Path, *, allowed_root: Optional[str] = None) -> Dict[str, Any]:
    """Sides of a file's diff against HEAD. `real` has already passed the root and sensitive-name check."""
    boundary = Path(allowed_root) if allowed_root else None
    folder = real.parent
    while not folder.is_dir() and folder != folder.parent and folder != boundary:
        folder = folder.parent
    if boundary is not None:
        try:
            if boundary.resolve(strict=True) != boundary or folder.resolve() != folder or not folder.is_relative_to(boundary):
                return {"available": False, "reason": "outside"}
        except (OSError, RuntimeError):
            return {"available": False, "reason": "missing"}
    toplevel, reason = _toplevel(str(folder))
    if toplevel is None:
        return {"available": False, "reason": reason}
    try:
        rel = real.relative_to(Path(toplevel).resolve()).as_posix()
    except ValueError:
        return {"available": False, "reason": "no_repo"}
    code, head = _capture([*SAFE_GIT, "-C", toplevel, "rev-parse", "--verify", "HEAD^{commit}"], 128)
    if code != 0:
        return {"available": False, "reason": "previous_unavailable"}
    base = head.decode("ascii").strip()
    raw, truncated, absent = _head_blob(toplevel, base, rel)
    if raw is not None and b"\x00" in raw:
        return {"available": False, "reason": "binary"}
    try:
        current = code_files.read_for_viewer(str(real), [allowed_root or toplevel], canonical=allowed_root is not None)
    except code_files.CodeReadError as err:
        if err.reason != "missing":
            return {"available": False, "reason": err.reason}
        if raw is None:
            return {"available": False, "reason": "missing" if absent else "previous_unavailable", "base": base}
        return {"available": True, "status": "deleted", "old": raw.decode("utf-8", "replace"), "new": "",
                "complete": not truncated, "truncated": truncated, "base": base}
    if raw is None and not absent:
        return {"available": True, "status": "unknown", "reason": "previous_unavailable", "base": base,
                "old": "", "new": current["text"], "complete": False, "truncated": False}
    old, new = "" if raw is None else raw.decode("utf-8", "replace"), current["text"]
    if os.name == "nt" and raw is not None:
        # Git on Windows may store LF while the worktree uses CRLF.
        old, new = old.replace("\r\n", "\n"), new.replace("\r\n", "\n")
    return {"available": True, "status": "new" if raw is None else "modified", "old": old, "new": new,
            "complete": not truncated, "truncated": truncated, "base": base}
