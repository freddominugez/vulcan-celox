"""Branches and worktrees with unreconciled work: agent sessions crossed with the real git.

Read-only: `git --no-optional-locks` stops `status` from rewriting .git/index, and every command goes
through core/runner.py with a timeout. The app never commits, pushes or removes a worktree; it only shows and copies prompts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import time
from typing import Callable, Dict, List, Optional, Sequence

from vulcan_celox.core.agents import rules
from vulcan_celox.core.agents.model import AgentSession, parse_iso

TIMEOUT = 5.0
IDLE_DAYS = 3
STATE_ORDER = ("sem commit", "sem push", "sem upstream", "PR aberto", "publicado", "nada editado", "sem git")


# the analyzed repository is third-party: core.fsmonitor would make git status run a program defined
# in its .git/config, and untrackedCache would write to .git; --no-optional-locks stops the index from being rewritten
SAFE_GIT = ("git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false", "--no-optional-locks")


def _git(path: str, *args: str) -> List[str]:
    return [*SAFE_GIT, "-C", path, *args]


@dataclass
class GitState:
    path: str
    is_repo: bool = False
    branch: Optional[str] = None
    dirty: int = 0
    ahead: Optional[int] = None  # None: sem upstream
    worktrees: List[Dict[str, str]] = field(default_factory=list)


def git_state(runner, path: str, worktrees: bool = False) -> GitState:
    state = GitState(path)
    probe = runner.run(_git(path, "rev-parse", "--is-inside-work-tree"), timeout=TIMEOUT)
    if not probe.ok or probe.stdout.strip() != "true":
        return state
    state.is_repo = True
    head = runner.run(_git(path, "rev-parse", "--abbrev-ref", "HEAD"), timeout=TIMEOUT)
    state.branch = head.stdout.strip() or None if head.ok else None
    status = runner.run(_git(path, "status", "--porcelain"), timeout=TIMEOUT)
    state.dirty = len([line for line in status.stdout.splitlines() if line.strip()]) if status.ok else 0
    ahead = runner.run(_git(path, "rev-list", "--count", "@{u}..HEAD"), timeout=TIMEOUT)
    if ahead.ok and ahead.stdout.strip().isdigit():
        state.ahead = int(ahead.stdout.strip())
    if worktrees:
        listing = runner.run(_git(path, "worktree", "list", "--porcelain"), timeout=TIMEOUT)
        state.worktrees = parse_worktrees(listing.stdout) if listing.ok else []
    return state


class GitCache:
    """Git state per folder cached for `ttl` seconds: the Branches screen does not run git on every refresh."""

    def __init__(self, runner, ttl: float = 30.0, clock: Callable[[], float] = time.monotonic):
        self.runner = runner
        self.ttl = ttl
        self.clock = clock
        self._items: Dict[tuple, tuple] = {}

    def state(self, path: str, worktrees: bool = False) -> GitState:
        key = (path, worktrees)
        hit = self._items.get(key)
        if hit and self.clock() - hit[0] < self.ttl:
            return hit[1]
        state = git_state(self.runner, path, worktrees)
        self._items[key] = (self.clock(), state)
        return state

    def clear(self) -> None:
        self._items.clear()


def parse_worktrees(text: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    current: Dict[str, str] = {}
    for line in (text or "").splitlines() + [""]:
        if not line.strip():
            if current.get("path"):
                out.append(current)
            current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            current["path"] = value
        elif key == "branch":
            current["branch"] = value.replace("refs/heads/", "", 1)
        elif key in ("detached", "bare", "prunable", "locked"):
            current[key] = value or "true"
    return out


def _days_since(iso: Optional[str], now: datetime) -> Optional[int]:
    dt = parse_iso(iso)
    return max(0, (now - dt).days) if dt else None


def _row_state(git: Optional[GitState], branch: Optional[str], sessions: Sequence[AgentSession]) -> str:
    edited = any(s.edited_total() for s in sessions)
    if git is not None and not git.is_repo:
        return "sem git"
    if git is not None and branch and git.branch == branch:
        if git.dirty:
            return "sem commit"
        if git.ahead is None and edited:
            return "sem upstream"
        if git.ahead:
            return "sem push"
    elif sessions and any(s.published in ("none", "committed") for s in sessions if s.edited_total()):
        # branch not open in any folder: what the sessions recorded counts
        return "sem commit" if all(s.published == "none" for s in sessions if s.edited_total()) else "sem push"
    if any(s.pr_opened for s in sessions):
        return "PR aberto"
    return "publicado" if edited or (git is not None and git.ahead == 0) else "nada editado"


def build(sessions: Sequence[AgentSession], runner, now: Optional[datetime] = None) -> List[Dict]:
    """One block per project, one row per branch or worktree, worst situation first.
    `runner` can be a GitCache (used by the API) or a plain runner (no cache)."""
    now = now or datetime.now(timezone.utc)
    cache = runner if isinstance(runner, GitCache) else GitCache(runner, ttl=0)
    by_root: Dict[str, List[AgentSession]] = {}
    for s in sessions:
        by_root.setdefault(s.project_root or s.cwd, []).append(s)
    projects = []
    for root, group in by_root.items():
        if not root:
            continue
        main = cache.state(root, worktrees=True)
        states = {root: main}
        rows: Dict[tuple, Dict] = {}
        for s in group:
            path = (rules.worktree_path(s.cwd) or s.cwd) if s.worktree else root
            if path not in states:
                states[path] = cache.state(path)
            branch = s.git_branch or states[path].branch  # Codex 0.166.0 does not record the branch
            row = rows.setdefault((path, branch), {"path": path, "branch": branch, "worktree": s.worktree, "sessions": []})
            row["sessions"].append(s)
        for wt in main.worktrees:
            if wt["path"] != root and (wt["path"], wt.get("branch")) not in rows:
                states[wt["path"]] = cache.state(wt["path"])
                rows[(wt["path"], wt.get("branch"))] = {"path": wt["path"], "branch": wt.get("branch"),
                                                        "worktree": wt["path"].rstrip("/").rsplit("/", 1)[-1], "sessions": []}
        out_rows = []
        for (path, branch), row in rows.items():
            group_s = row["sessions"]
            git = states.get(path)
            state = _row_state(git, branch, group_s)
            last = max((s.last_activity_at for s in group_s), default=None)
            idle = _days_since(last, now)
            stale = (state in ("sem commit", "sem push", "sem upstream") and idle is not None and idle >= IDLE_DAYS
                     and not any(s.is_active for s in group_s))
            out_rows.append({
                "path": path, "branch": branch, "worktree": row["worktree"], "state": state,
                "stale_days": idle if stale else None, "orphan_worktree": bool(row["worktree"]) and not group_s,
                "dirty": git.dirty if git and git.branch == branch else None,
                "ahead": git.ahead if git and git.branch == branch else None,
                "last_activity_at": last,
                "sessions": [{"id": s.id, "agent": s.agent, "is_active": s.is_active, "last_activity_at": s.last_activity_at,
                              "published": s.published, "theme": s.theme} for s in group_s],
            })
        out_rows.sort(key=lambda r: (STATE_ORDER.index(r["state"]), -(r["stale_days"] or 0), r["branch"] or ""))
        projects.append({"project": group[0].project_name, "root": root, "is_repo": main.is_repo,
                         "current_branch": main.branch, "rows": out_rows})
    projects.sort(key=lambda p: min((STATE_ORDER.index(r["state"]) for r in p["rows"]), default=len(STATE_ORDER)))
    return projects
