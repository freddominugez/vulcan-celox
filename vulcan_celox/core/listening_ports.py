"""Portas em escuta que cada aba abriu: só os processos do PTY e seus descendentes, nunca os do resto da máquina."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

TTL = 10.0
TIMEOUT = 5.0
LISTEN = "0A"


def process_tree(runner) -> Optional[Dict[int, List[int]]]:
    """pai -> filhos. None se o `ps` não rodou."""
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
    """Saída de `lsof -F pcn`: (pid, porta, comando). `n` termina em :porta, com ou sem endereço."""
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
        return [], "lsof não rodou"
    return parse_lsof(result.stdout), ""  # lsof sai com 1 quando nada escuta


def proc_listening(proc_root: Path) -> Dict[str, int]:
    """Inode do socket -> porta, em /proc/net/tcp e tcp6, só os em escuta."""
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
            continue  # o processo acabou ou é de outro usuário
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
        """`tabs`: (id da aba, pid do PTY). Falha vira lista vazia com motivo, nunca erro."""
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
        children = process_tree(self.runner)
        if children is None:
            return {"ports": {}, "reason": "ps não rodou"}
        owners: Dict[int, str] = {}
        for tab, root in tabs:
            for pid in descendants(children, root):
                owners.setdefault(pid, tab)
        rows, reason = lsof_ports(self.runner, owners) if self.platform == "darwin" else proc_ports(self.proc_root, owners)
        out: Dict[str, Dict[int, Dict]] = {}
        for pid, port, command in rows:
            if pid in owners:  # o que não é da aba não aparece, mesmo se o comando devolver
                out.setdefault(owners[pid], {}).setdefault(port, {"port": port, "pid": pid, "command": command})
        return {"ports": {tab: sorted(ports.values(), key=lambda p: p["port"]) for tab, ports in out.items()}, "reason": reason}
