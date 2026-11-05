"""One folder of a project at a time, for the Code screen. Read-only. The repository is third-party, so the only git command
here is `ls-files -o -i`, which tests/test_files_seguranca.py proves does not run anything from the repository."""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from vulcan_celox.core import code_files
from vulcan_celox.core.agents.repos import SAFE_GIT
from vulcan_celox.core.runner import capture

MAX_ENTRIES = 5000
FIXED_IGNORED = frozenset({"node_modules", "vendor", "dist", "build", "__pycache__", ".venv", ".next", "target"})
HIDDEN = frozenset({".git"})
GIT_TIMEOUT = 5.0
GIT_OUTPUT = 16 * 1024 * 1024
IGNORE_TTL = 30.0
SEARCH_RESULTS = 500
SEARCH_TIMEOUT = 10.0
SEARCH_OUTPUT = 8 * 1024 * 1024
SEARCH_LINE = 300
_SEPARATORS = re.compile(r"[\\/]" if os.name == "nt" else r"/")


def clean_rel(path: Optional[str]) -> str:
    """A path relative to the root, or "" for the root itself. Absolute paths and `..` are refused before touching the disk."""
    path = path or ""
    pure = Path(path)
    if "\x00" in path or pure.is_absolute() or pure.anchor or pure.drive or path.startswith(("/", "\\")):
        raise code_files.CodeReadError(400, "invalid", "caminho inválido")
    parts = [p for p in _SEPARATORS.split(path) if p and p != "."]
    if ".." in parts:
        raise code_files.CodeReadError(400, "invalid", "caminho inválido")
    return "/".join(parts)


def display_name(name: str) -> str:
    """A name that is not valid UTF-8 cannot travel in a URL: it shows with replacement characters and does not open."""
    return name.encode("utf-8", "surrogateescape").decode("utf-8", "replace")


def has_bad_name(name: str) -> bool:
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        return True
    return False


class Ignored:
    """What git says is ignored in the root or, without git or past the time limit, the fixed list of names."""

    def __init__(self, paths: Optional[Set[str]] = None):
        self.paths = paths  # relative paths, without the final bar; None = fixed list
        self.fixed = paths is None

    def matches(self, rel: str, is_dir: bool = True) -> bool:
        if not rel:
            return False
        parts = rel.split("/")
        if self.fixed:
            return any(p in FIXED_IGNORED for p in (parts if is_dir else parts[:-1]))
        return any("/".join(parts[:i]) in self.paths for i in range(1, len(parts) + 1))


def inside_its_repository(root: str) -> bool:
    """False if the repository's own config (core.worktree) moved the working tree away from this folder."""
    code, raw, _ = capture([*SAFE_GIT, "-C", root, "rev-parse", "--show-toplevel"], 8192, GIT_TIMEOUT)
    if code != 0 or not raw.strip():
        return False
    top = Path(raw.decode("utf-8", "surrogateescape").rstrip("\n"))
    try:
        return Path(root).resolve().is_relative_to(top.resolve())
    except (OSError, RuntimeError):
        return False


def git_ignored(root: str) -> Ignored:
    """The proof in tests/test_files_seguranca.py covers this command: no filter, fsmonitor or textconv runs."""
    if not inside_its_repository(root):
        return Ignored(None)
    code, raw, timed_out = capture([*SAFE_GIT, "-C", root, "ls-files", "-z", "-o", "-i", "--exclude-standard", "--directory"],
                                   GIT_OUTPUT, GIT_TIMEOUT)
    if code != 0 or timed_out or len(raw) > GIT_OUTPUT:
        return Ignored(None)
    return Ignored({p.decode("utf-8", "surrogateescape").rstrip("/") for p in raw.split(b"\0") if p})


class IgnoreCache:
    """Listing a folder and each sweep ask the same question: git runs at most once per IGNORE_TTL for each root."""

    def __init__(self, source=git_ignored, ttl: float = IGNORE_TTL):
        self.source = source
        self.ttl = ttl
        self.lock = threading.Lock()
        self.items: Dict[str, Any] = {}

    def get(self, root: str) -> Ignored:
        now = time.monotonic()
        with self.lock:
            cached = self.items.get(root)
        if cached and now - cached[0] < self.ttl:
            return cached[1]
        value = self.source(root)
        with self.lock:
            if len(self.items) > 100:
                self.items.clear()
            self.items[root] = (now, value)
        return value


def git_search(root: str, text: str, limit: int = SEARCH_RESULTS, seconds: float = SEARCH_TIMEOUT) -> Dict[str, Any]:
    """Text in the tracked files, without running anything from the repository: `grep --no-textconv` does not go through filters."""
    probe, _, _ = capture([*SAFE_GIT, "--version"], 256, GIT_TIMEOUT)
    if probe is None:
        return {"available": False, "reason": "no_git"}
    if not inside_its_repository(root):
        return {"available": False, "reason": "no_repo"}
    code, raw, timed_out = capture([*SAFE_GIT, "-C", root, "grep", "--no-textconv", "--no-color", "--no-column", "--no-full-name",
                                    "-z", "-n", "-I", "-F", "-e", text, "--", "."], SEARCH_OUTPUT, seconds)
    if code is None:
        return {"available": False, "reason": "no_git"}
    if code not in (0, 1) and not timed_out and len(raw) <= SEARCH_OUTPUT:
        return {"available": False, "reason": "no_repo"}
    results: List[Dict[str, Any]] = []
    cut = timed_out or len(raw) > SEARCH_OUTPUT
    for chunk in raw.split(b"\n"):
        parts = chunk.split(b"\0", 2)
        if len(parts) != 3:  # the last piece of a cut output, or an unexpected format
            continue
        rel = parts[0].decode("utf-8", "surrogateescape")
        if has_bad_name(rel) or code_files.is_sensitive(rel):
            continue
        if len(results) >= limit:
            cut = True
            break
        try:
            line = int(parts[1])
        except ValueError:
            continue
        results.append({"rel": rel, "line": line, "text": parts[2].decode("utf-8", "replace")[:SEARCH_LINE]})
    return {"available": True, "results": results, "truncated": cut}


def sensitive_entry(rel: str, is_dir: bool) -> bool:
    return code_files.is_sensitive(rel) or (is_dir and rel.rsplit("/", 1)[-1].lower() in code_files.SENSITIVE_DIRS)


def real_folder(root: str, rel: str) -> Path:
    """The folder itself, without passing through a link: links appear in the tree but are not followed."""
    base = Path(root).resolve()
    target = base / rel if rel else base
    try:
        real = target.resolve()
    except (OSError, RuntimeError):
        raise code_files.CodeReadError(400, "invalid", "caminho inválido") from None
    if real != target:
        raise code_files.CodeReadError(403, "link", "link simbólico não é seguido")
    if rel and any(p.lower() in HIDDEN or p.lower() in code_files.SENSITIVE_DIRS for p in rel.split("/")):
        raise code_files.CodeReadError(403, "sensitive", "pasta com nome sensível não é exibida")
    return real


def _entry(item: os.DirEntry, rel: str, is_dir: bool, is_link: bool, ignored: Ignored) -> Dict[str, Any]:
    try:
        info = item.stat(follow_symlinks=False)
        size, mtime = (0 if is_dir else info.st_size), info.st_mtime
    except OSError:
        size, mtime = 0, 0
    bad = has_bad_name(item.name)
    out = {"name": display_name(item.name), "rel": display_name(rel), "kind": "link" if is_link else "dir" if is_dir else "file",
           "size": size, "mtime": mtime, "sensitive": sensitive_entry(rel, is_dir), "ignored": ignored.matches(rel, is_dir)}
    if bad:
        out["bad_name"] = True
    return out


def list_folder(root: str, rel: str, ignored: Ignored, limit: int = MAX_ENTRIES) -> Dict[str, Any]:
    real = real_folder(root, rel)
    try:
        with os.scandir(real) as it:
            items = [i for i in it if i.name.lower() not in HIDDEN]
    except FileNotFoundError:
        raise code_files.CodeReadError(404, "missing", "a pasta não existe mais") from None
    except NotADirectoryError:
        raise code_files.CodeReadError(400, "not_dir", "não é uma pasta") from None
    except OSError:
        raise code_files.CodeReadError(403, "unreadable", "não foi possível abrir a pasta") from None
    rows: List[Any] = []
    for item in items:
        try:
            is_link = item.is_symlink()
            is_dir = not is_link and item.is_dir(follow_symlinks=False)
        except OSError:
            is_link = is_dir = False
        rows.append((not is_dir, item.name.casefold(), item.name, item, is_dir, is_link))
    rows.sort(key=lambda r: r[:3])
    entries = [_entry(r[3], f"{rel}/{r[2]}" if rel else r[2], r[4], r[5], ignored) for r in rows[:limit]]
    return {"root": str(Path(root).resolve()), "path": rel, "entries": entries, "truncated": len(rows) > limit,
            "total": len(rows), "ignored": ignored.matches(rel), "fixed_ignore": ignored.fixed}
