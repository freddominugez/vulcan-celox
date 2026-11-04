"""Listening ports each tab opened: only the PTY's processes and their descendants, never the rest of the machine's."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from vulcan_celox.core.i18n import tr

TTL = 10.0
TIMEOUT = 5.0
LISTEN = "0A"


def parse_netstat(text: str, pids: Iterable[int]) -> List[Tuple[int, int, str]]:
    """Output of `netstat -ano -p tcp`: (pid, port, command), only for those in `pids` and listening."""
    wanted = set(pids)
    found: List[Tuple[int, int, str]] = []
    for line in text.splitlines():
        cols = line.split()
        if len(cols) >= 5 and cols[0].upper().startswith("TCP") and cols[3].upper() == "LISTENING" and cols[4].isdigit():
            port = cols[1].rsplit(":", 1)[-1]
            if int(cols[4]) in wanted and port.isdigit():
                found.append((int(cols[4]), int(port), ""))
    return found


def netstat_ports(runner, pids: Iterable[int]) -> Tuple[List[Tuple[int, int, str]], str]:
    pids = list(pids)
    rows: List[Tuple[int, int, str]] = []
    for protocol in ("tcp", "tcpv6"):
        result = runner.run(["netstat", "-ano", "-p", protocol], timeout=TIMEOUT)
        if result.code in (126, 127) or result.timed_out:
            return [], "netstat não rodou"
        rows += parse_netstat(result.stdout, pids)
    return rows, ""


def process_tree(runner, platform: str = sys.platform) -> Optional[Dict[int, List[int]]]:
    """parent -> children. None if `ps` did not run."""
    if platform == "win32":
        from vulcan_celox.core.win32 import children_map
        return children_map()
    result = runner.run(["ps", "-A", "-o", "pid=,ppid="], timeout=TIMEOUT)
    if not result.ok:
        return None
    children: Dict[int, List[int]] = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            children.setdefault(int(parts[1]), []).append(int(parts[0]))
    return children


def descendants(children: Dict[int, List[int]], root: int) -> Set[int]:
    seen: Set[int] = set()
    stack = [root]
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        stack.extend(children.get(pid, []))
    return seen


def parse_lsof(text: str) -> List[Tuple[int, int, str]]:
    """Output of `lsof -F pcn`: (pid, port, command). `n` ends in :port, with or without an address."""
    found: List[Tuple[int, int, str]] = []
    pid, command = 0, ""
    for line in text.splitlines():
        field, value = line[:1], line[1:]
        if field == "p" and value.isdigit():
            pid, command = int(value), ""
        elif field == "c":
            command = value
        elif field == "n":
            port = value.rsplit(":", 1)[-1]
            if pid and port.isdigit():
                found.append((pid, int(port), command))
    return found


def lsof_ports(runner, pids: Iterable[int]) -> Tuple[List[Tuple[int, int, str]], str]:
    wanted = ",".join(str(p) for p in sorted(pids))
    if not wanted:
        return [], ""
    result = runner.run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-p", wanted, "-F", "pcn"], timeout=TIMEOUT)
    if result.code in (126, 127) or result.timed_out:
        return [], tr("lsof não rodou")
    return parse_lsof(result.stdout), ""  # lsof exits with 1 when nothing is listening


def proc_listening(proc_root: Path) -> Dict[str, int]:
    """Socket inode -> port, in /proc/net/tcp and tcp6, listening ones only."""
    inodes: Dict[str, int] = {}
    for name in ("tcp", "tcp6"):
        try:
            lines = (proc_root / "net" / name).read_text(encoding="ascii", errors="replace").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            cols = line.split()
            if len(cols) > 9 and cols[3] == LISTEN and ":" in cols[1]:
                inodes[cols[9]] = int(cols[1].rsplit(":", 1)[1], 16)
    return inodes


def proc_ports(proc_root: Path, pids: Iterable[int]) -> Tuple[List[Tuple[int, int, str]], str]:
    inodes = proc_listening(proc_root)
    found: List[Tuple[int, int, str]] = []
    for pid in pids:
        folder = proc_root / str(pid)
        try:
            links = [os.readlink(folder / "fd" / fd) for fd in os.listdir(folder / "fd")]
            command = (folder / "comm").read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue  # the process ended or belongs to another user
        for link in links:
            if link.startswith("socket:[") and link[8:-1] in inodes:
                found.append((pid, inodes[link[8:-1]], command))
    return found, ""


class PortWatcher:
    def __init__(self, runner, clock: Callable[[], float] = time.monotonic, platform: Optional[str] = None,
                 proc_root: Path = Path("/proc")):
        self.runner, self.clock, self.proc_root = runner, clock, proc_root
        self.platform = platform or sys.platform
        self.lock = threading.Lock()
        self.cached: Optional[Tuple[float, Tuple, Dict]] = None

    def ports(self, tabs: List[Tuple[str, int]]) -> Dict:
        """`tabs`: (tab id, PTY pid). A failure becomes an empty list with a reason, never an error."""
        key = tuple(sorted(tabs))
        now = self.clock()
        with self.lock:
            if self.cached and self.cached[1] == key and now - self.cached[0] < TTL:
                return self.cached[2]
            data = self._read(tabs)
            self.cached = (now, key, data)
            return data

    def _read(self, tabs: List[Tuple[str, int]]) -> Dict:
        if not tabs:
            return {"ports": {}, "reason": ""}
        children = process_tree(self.runner, self.platform)
        if children is None:
            return {"ports": {}, "reason": tr("ps não rodou")}
        owners: Dict[int, str] = {}
        for tab, root in tabs:
            for pid in descendants(children, root):
                owners.setdefault(pid, tab)
        if self.platform == "win32":
            rows, reason = netstat_ports(self.runner, owners)
        elif self.platform == "darwin":
            rows, reason = lsof_ports(self.runner, owners)
        else:
            rows, reason = proc_ports(self.proc_root, owners)
        out: Dict[str, Dict[int, Dict]] = {}
        for pid, port, command in rows:
            if pid in owners:  # what does not belong to the tab does not appear, even if the command returns it
                out.setdefault(owners[pid], {}).setdefault(port, {"port": port, "pid": pid, "command": command})
        return {"ports": {tab: sorted(ports.values(), key=lambda p: p["port"]) for tab, ports in out.items()}, "reason": reason}
