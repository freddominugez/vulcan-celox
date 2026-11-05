"""Git state of each file, from the index compared with the disk, without running anything from the repository.

`git status`, `git diff` on the worktree and `ls-files -m` run the repository's clean filter and fsmonitor. Here git only lists
the index (`ls-files -s --debug`) and the untracked files; sizes and dates are compared with `lstat`, and no content is read.
A file that was only touched counts as changed: telling them apart would need the clean filter."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from vulcan_celox.core.agents.repos import GITLINK, SAFE_GIT, _unquote
from vulcan_celox.core.runner import capture

BUDGET = 20_000  # the same as the photo of the Code screen
TIMEOUT = 5.0
OUTPUT = 32 * 1024 * 1024
CHANGED, DELETED, UNTRACKED = "M", "D", "U"


def _state(full: str, size: str, mtime: Optional[str]) -> Optional[str]:
    try:
        info = os.lstat(full)
    except FileNotFoundError:
        return DELETED
    except OSError:
        return CHANGED
    seconds, _, nanos = (mtime or "0:0").partition(":")
    if str(info.st_size) != size or int(info.st_mtime) != int(seconds):
        return CHANGED
    if int(nanos or 0) != 0 and info.st_mtime_ns % 1000000000 != int(nanos):
        return CHANGED
    return None


def index_marks(path: str, listing: str, limit: Optional[int] = None) -> Tuple[Dict[str, str], bool]:
    """(changed and deleted tracked files, whether the index had more entries than `limit`)."""
    marks: Dict[str, str] = {}
    name, mode, mtime, seen = "", "", None, 0
    for line in listing.splitlines():
        if line.startswith("  mtime: "):
            mtime = line[9:].strip()
        elif line.startswith("  size: "):
            size = line[8:].split("\t", 1)[0].strip()
            if name and mode != GITLINK:
                state = _state(os.path.join(path, name), size, mtime)
                if state:
                    marks[name] = state
        elif not line.startswith("  ") and "\t" in line:
            seen += 1
            if limit is not None and seen > limit:
                return marks, True
            head, raw = line.split("\t", 1)
            mode, name, mtime = head.split(" ", 1)[0], _unquote(raw), None
    return marks, False


def untracked(listing: str, limit: Optional[int] = None) -> Tuple[List[str], bool]:
    """New files and folders (`ls-files -o --directory`), with the final bar of a folder removed."""
    found = [_unquote(line).rstrip("/") for line in listing.splitlines() if line.strip()]
    if limit is not None and len(found) > limit:
        return found[:limit], True
    return found, False


def from_listings(path: str, index_listing: str, loose_listing: str, limit: Optional[int] = None) -> Dict[str, Any]:
    marks, cut = index_marks(path, index_listing, limit)
    loose, cut_loose = untracked(loose_listing, limit)
    for rel in loose:
        marks[rel] = UNTRACKED
    return {"marks": marks, "truncated": cut or cut_loose}


def _run(root: str, *args: str) -> Optional[str]:
    code, raw, timed_out = capture([*SAFE_GIT, "-C", root, *args], OUTPUT, TIMEOUT)
    if code != 0 or timed_out or len(raw) > OUTPUT:
        return None
    return raw.decode("utf-8", "surrogateescape")


def collect(root: str, limit: int = BUDGET) -> Dict[str, Any]:
    """Marks of a Code screen root, relative to it. A folder outside its repository's working tree (core.worktree) gets none."""
    from vulcan_celox.core.file_tree import inside_its_repository
    empty = {"marks": {}, "truncated": False, "branch": None, "repo": False}
    if not inside_its_repository(root):
        return empty
    listing = _run(root, "ls-files", "-s", "--debug")
    loose = _run(root, "ls-files", "-o", "--exclude-standard", "--directory", "--no-empty-directory")
    if listing is None or loose is None:
        return {**empty, "repo": True, "truncated": True}
    head = _run(root, "symbolic-ref", "--short", "-q", "HEAD")  # also names a branch with no commit yet; detached gives none
    branch = head.strip() or None if head else None
    return {**from_listings(root, listing, loose, limit), "branch": branch, "repo": True}
