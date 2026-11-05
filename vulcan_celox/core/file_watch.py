"""Live changes of a project folder for the Code screen. Compares photos of the disk made with os.scandir: no content is read,
no link is followed, what is ignored is pruned, and nothing here asks git what changed, because the commands that know run
programs from the repository (tests/test_files_seguranca.py)."""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from vulcan_celox.core import code_files
from vulcan_celox.core.file_tree import HIDDEN, Ignored, has_bad_name, sensitive_entry

BUDGET = 20000
IDLE_SECONDS = 30.0
MIN_INTERVAL = 1.0
MAX_INTERVAL = 15.0
MAX_EVENTS = 2000
POLL_WAIT = 0.25
Photo = Tuple[int, int, str]


def next_interval(scan_seconds: float, low: float = MIN_INTERVAL, high: float = MAX_INTERVAL) -> float:
    return min(high, max(low, scan_seconds * 10))


def _read_folder(path: str) -> Optional[Dict[str, Photo]]:
    """name -> (size, mtime_ns, kind) without following links. None if the folder does not exist; raises PermissionError."""
    out: Dict[str, Photo] = {}
    try:
        with os.scandir(path) as it:
            for item in it:
                if item.name.lower() in HIDDEN or has_bad_name(item.name):
                    continue
                try:
                    info = item.stat(follow_symlinks=False)
                    kind = "link" if item.is_symlink() else "dir" if item.is_dir(follow_symlinks=False) else "file"
                except OSError:
                    continue  # it disappeared between listing and looking: the next sweep tells
                out[item.name] = (0 if kind == "dir" else info.st_size, 0 if kind == "dir" else info.st_mtime_ns, kind)
    except (FileNotFoundError, NotADirectoryError):
        return None
    return out


def _join(folder: str, name: str) -> str:
    return f"{folder}/{name}" if folder else name


def _parent(rel: str) -> str:
    return rel.rsplit("/", 1)[0] if "/" in rel else ""


@dataclass
class _Sweep:
    events: List[Dict[str, Any]]
    ignored: Ignored
    seen: int = 0
    over: bool = False


class RootWatch:
    """One thread per root with the screen open. It stops if nobody asks for `idle` seconds."""

    def __init__(self, root: str, ignored: Callable[[str], Ignored], first_seq: int, budget: int = BUDGET, idle: float = IDLE_SECONDS,
                 low: float = MIN_INTERVAL, high: float = MAX_INTERVAL, on_stop: Optional[Callable[["RootWatch"], None]] = None):
        self.root = root
        self.ignored = ignored
        self.budget = budget
        self.idle = idle
        self.low, self.high = low, high
        self.on_stop = on_stop
        self.lock = threading.Lock()
        self.dirs: Dict[str, Dict[str, Photo]] = {}
        self.events: deque = deque(maxlen=MAX_EVENTS)
        self.floor = first_seq
        self.seq = first_seq
        self.partial = False
        self.missing = False
        self.interval = low
        self.scan_seconds = 0.0
        self.opened: Set[str] = set()
        self.open_file = ""
        self.last_poll = time.monotonic()
        self.ready = threading.Event()
        self.wake = threading.Event()
        self.swept = threading.Event()
        self.last_sweep = -1000.0
        self.halt = threading.Event()
        self.thread = threading.Thread(target=self._run, name="vulcan-file-watch", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.halt.set()
        self.wake.set()

    # ── sweep ───────────────────────────────────────────────────────────
    def _record(self, sweep: _Sweep, rel: str, change: str, kind: str) -> None:
        is_dir = kind == "dir"
        sweep.events.append({"rel": rel, "change": change, "kind": kind, "ignored": sweep.ignored.matches(rel, is_dir),
                             "sensitive": sensitive_entry(rel, is_dir), "agent": None, "at": time.time()})

    def _forget(self, sweep: _Sweep, rel: str) -> None:
        """A folder that disappeared takes what we knew inside it along."""
        children = self.dirs.pop(rel, None)
        for name, photo in (children or {}).items():
            child = _join(rel, name)
            if photo[2] == "dir":
                self._forget(sweep, child)
            self._record(sweep, child, "deleted", photo[2])

    def _visit(self, sweep: _Sweep, rel: str, announce_new: bool) -> List[Tuple[str, bool]]:
        """Compares one folder with its last photo and returns the subfolders to visit, each with `was it just created?`."""
        path = os.path.join(self.root, rel) if rel else self.root
        try:
            now = _read_folder(path)
        except OSError:
            return []  # no permission now: keeps the last photo instead of inventing a deletion
        if now is None:
            return []
        before = self.dirs.get(rel)
        self.dirs[rel] = now
        sweep.seen += len(now)
        created: Set[str] = set()
        if before is None:
            if announce_new:
                for name, photo in now.items():
                    self._record(sweep, _join(rel, name), "added", photo[2])
                    created.add(name)
        else:
            for name, photo in now.items():
                old = before.get(name)
                if old is None:
                    self._record(sweep, _join(rel, name), "added", photo[2])
                    created.add(name)
                elif old != photo:
                    self._record(sweep, _join(rel, name), "modified", photo[2])
            for name, photo in before.items():
                if name not in now:
                    if photo[2] == "dir":
                        self._forget(sweep, _join(rel, name))
                    self._record(sweep, _join(rel, name), "deleted", photo[2])
        return [(_join(rel, name), name in created) for name, photo in now.items() if photo[2] == "dir"]

    def _prune(self, sweep: _Sweep, rel: str) -> bool:
        return sweep.ignored.matches(rel) or rel.rsplit("/", 1)[-1].lower() in code_files.SENSITIVE_DIRS

    def _walk(self, sweep: _Sweep) -> None:
        stack: List[Tuple[str, bool]] = [("", False)]
        while stack:
            rel, created = stack.pop()
            for child, fresh in self._visit(sweep, rel, created):
                if not self._prune(sweep, child):
                    stack.append((child, fresh))
            if sweep.seen > self.budget:
                sweep.over = True
                return

    def _shallow(self, sweep: _Sweep, folders: Iterable[str]) -> None:
        for rel in folders:
            self._visit(sweep, rel, False)

    def sweep(self) -> None:
        with self.lock:
            opened, open_file = set(self.opened), self.open_file
        started = time.perf_counter()
        self.last_sweep = time.monotonic()
        sweep = _Sweep([], self.ignored(self.root))
        if not os.path.isdir(self.root):
            if not self.missing:
                self._forget(sweep, "")
            self.missing = True
        else:
            self.missing = False
            first = not self.dirs
            if not self.partial:
                self._walk(sweep)
                if sweep.over:
                    self.partial = True
                    if first:  # budget exceeded on the opening photo: nothing to announce
                        sweep.events.clear()
                    self.dirs = {k: v for k, v in self.dirs.items() if k in opened or k == ""}
            targets = set(opened)
            if self.partial:
                targets.add("")
                if open_file:
                    targets.add(_parent(open_file))
            else:
                targets = {t for t in targets if t not in self.dirs or self._prune(sweep, t)}
            self._shallow(sweep, sorted(targets))
        self.scan_seconds = time.perf_counter() - started
        self.interval = next_interval(self.scan_seconds, self.low, self.high)
        with self.lock:
            for event in sweep.events:
                self.seq += 1
                self.events.append({"seq": self.seq, **event})

    def _run(self) -> None:
        try:
            while not self.halt.is_set():
                try:
                    self.sweep()
                except Exception:  # a sweep that fails must not end the watching: the next one tries again
                    pass
                self.swept.set()
                self.ready.set()
                self.wake.wait(self.interval)
                self.wake.clear()
                if time.monotonic() - self.last_poll > self.idle:
                    break
        finally:
            self.ready.set()
            if self.on_stop:
                self.on_stop(self)

    # ── what the screen asks ────────────────────────────────────────────
    def poll(self, since: Optional[int], opened: Iterable[str], open_file: str) -> Dict[str, Any]:
        opened = set(opened)
        # the sweep that was due runs just before the answer: a write takes one polling interval to show, not two
        if time.monotonic() - self.last_sweep >= self.interval * 0.9 and self.ready.is_set():
            self.swept.clear()
            self.wake.set()
            self.swept.wait(min(POLL_WAIT, self.scan_seconds * 2 + 0.01))
        with self.lock:
            self.last_poll = time.monotonic()
            news = bool(opened - self.opened)
            self.opened, self.open_file = opened, open_file
            events = list(self.events)
            cursor, partial, missing = self.seq, self.partial, self.missing
        if news:
            self.wake.set()  # a folder just opened enters the photo now, not at the next sweep
        out: Dict[str, Any] = {"cursor": cursor, "events": [], "partial": partial, "reset": False, "missing": missing,
                               "interval": self.interval, "watching": sum(1 for _ in list(self.dirs))}
        if since is None:
            return out
        first = events[0]["seq"] if events else cursor + 1
        if since > cursor or since < self.floor or since < first - 1:
            out["reset"] = True
            return out
        out["events"] = [e for e in events if e["seq"] > since]
        return out

    def recent(self) -> List[Dict[str, Any]]:
        """The stored events themselves: who wrote a file may become known after the event."""
        with self.lock:
            return list(self.events)

    def photo_files(self, limit: int = BUDGET) -> List[str]:
        """Files in the current photo, for the quick open."""
        out: List[str] = []
        for folder, children in sorted(dict(self.dirs).items()):
            for name, photo in sorted(children.items()):
                if photo[2] != "dir":
                    out.append(_join(folder, name))
                    if len(out) >= limit:
                        return out
        return out


class FileWatches:
    """The live watchers. The sequence survives a watcher stopping: a cursor from before it is refused with `reset`."""

    def __init__(self, ignored: Callable[[str], Ignored], **options: Any):
        self.ignored = ignored
        self.options = options
        self.lock = threading.Lock()
        self.watches: Dict[str, RootWatch] = {}
        self.last_seq: Dict[str, int] = {}

    def _gone(self, watch: RootWatch) -> None:
        with self.lock:
            if self.watches.get(watch.root) is watch:
                del self.watches[watch.root]
            self.last_seq[watch.root] = watch.seq

    def watch(self, root: str) -> RootWatch:
        with self.lock:
            watch = self.watches.get(root)
            created = watch is None
            if created:
                watch = RootWatch(root, self.ignored, self.last_seq.get(root, 0) + 1, on_stop=self._gone, **self.options)
                self.watches[root] = watch
                watch.start()
        if created:
            watch.ready.wait(2.0)  # the opening photo is the reference: anything after it counts as a change
        return watch

    def poll(self, root: str, since: Optional[int], opened: Iterable[str], open_file: str) -> Dict[str, Any]:
        return self.watch(root).poll(since, opened, open_file)

    def stop(self, root: Optional[str] = None) -> None:
        with self.lock:
            targets = [w for r, w in self.watches.items() if root is None or r == root]
        for watch in targets:
            watch.stop()
