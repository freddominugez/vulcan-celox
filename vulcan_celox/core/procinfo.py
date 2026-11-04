"""Foreground group processes of a terminal.

Used to know whether a session's agent still runs in the paired tab: after Claude Code or Codex exits, the
tab becomes a plain shell and a pasted prompt would land in the shell. Linux reads /proc; macOS runs `ps` through the runner.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Tuple

from vulcan_celox.core.runner import Runner

Proc = Tuple[str, str]  # (executable name, command line)

# executables of each agent; native Claude Code runs from ~/.local/share/claude/versions/<version>
AGENT_EXECUTABLES = {
    "claude": {"claude"},
    "codex": {"codex"},
    "gemini": {"gemini"},
    "cursor": {"cursor-agent"},
}


def foreground_pgid(fd: int) -> Optional[int]:
    try:
        return os.tcgetpgrp(fd)
    except OSError:
        return None


def _from_proc(pgid: int, root: Path) -> List[Proc]:
    procs: List[Proc] = []
    for entry in root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text(encoding="utf-8", errors="replace")
            comm = stat[stat.index("(") + 1:stat.rindex(")")]
            fields = stat[stat.rindex(")") + 2:].split()
            if int(fields[2]) != pgid:  # estado, ppid, pgrp
                continue
            raw = (entry / "cmdline").read_bytes()
        except (OSError, ValueError, IndexError):
            continue  # the process exited mid-read
        procs.append((comm, raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()))
    return procs


def _from_ps(pgid: int, runner) -> Optional[List[Proc]]:
    result = runner.run(["ps", "-A", "-o", "pgid=", "-o", "args="], timeout=5)
    if result.code != 0:
        return None
    procs: List[Proc] = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit() and int(parts[0]) == pgid:
            args = parts[1]
            procs.append((os.path.basename(args.split()[0]), args))
    return procs


def group_processes(pgid: Optional[int], runner=None, proc_root: Path = Path("/proc")) -> Optional[List[Proc]]:
    """Processes of group `pgid`. None when it cannot be known (no /proc and no ps)."""
    if not pgid or pgid <= 0:
        return None
    try:
        if (proc_root / "self").is_dir():
            return _from_proc(pgid, proc_root)
        return _from_ps(pgid, runner or Runner())
    except OSError:
        return None


def agent_running(procs: List[Proc], agent: str) -> bool:
    """Some process is the agent: executable name, or a path component of the first two arguments
        (`node /opt/homebrew/bin/codex`, `/Users/x/.local/share/claude/versions/2.1.3`)."""
    names = AGENT_EXECUTABLES.get(agent, {agent})
    for comm, args in procs:
        candidates = {os.path.basename(comm.lstrip("-"))}
        for token in args.split()[:2]:
            candidates.update(part for part in token.lstrip("-").split("/") if part)
        if candidates & names:
            return True
    return False


def tab_runs_agent(terminal, agent: str) -> bool:
    """Is the agent still running in the foreground in this tab? When there is no way to know, a live tab counts."""
    if terminal is None or not getattr(terminal, "alive", False):
        return False
    foreground = terminal.foreground() if hasattr(terminal, "foreground") else None
    return foreground is None or agent_running(foreground, agent)
