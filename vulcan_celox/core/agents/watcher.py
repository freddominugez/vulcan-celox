"""Watches the Claude Code and Codex folders by os.stat polling and keeps the index up to date.

Scans every `interval` seconds; each file that changed waits `debounce` seconds with no further changes
(core/debounce.py) before being read from the saved offset. Never writes to the watched folders.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Tuple

from vulcan_celox.core.agents import discovery
from vulcan_celox.core.agents.index import AgentIndex
from vulcan_celox.core.debounce import Debouncer

INTERVAL = 2.0
DEBOUNCE = 0.3


class AgentWatcher:
    def __init__(self, index: AgentIndex, env: Optional[Mapping[str, str]] = None, interval: float = INTERVAL,
                 debounce: float = DEBOUNCE, clock: Callable[[], float] = time.monotonic,
                 on_change: Optional[Callable[[List[str]], None]] = None):
        self.index = index
        self.env = dict(os.environ if env is None else env)
        self.interval = interval
        self.debounce = debounce
        self.clock = clock
        self.on_change = on_change
        self.zst_ignored = 0
        self.last_scan: Optional[float] = None
        self.last_error: Optional[str] = None
        self._seen: Dict[str, Tuple[float, int]] = {}
        self._pending: Dict[str, Debouncer] = {}
        self._reading = 0
        self._changed: List[str] = []
        self._stop = threading.Event()
        self._lock = threading.Lock()  # the thread and a refresh requested by the API must not scan together
        self._thread: Optional[threading.Thread] = None

    # ── varredura ──────────────────────────────────────────────────────────
    def roots(self) -> Dict[str, List[str]]:
        return {"claude": [str(discovery.claude_root(self.env))],
                "codex": [str(p) for p in discovery.codex_roots(self.env)]}

    def files(self) -> List[Tuple[str, Path]]:
        claude = discovery.claude_root(self.env)
        out = [("claude", p) for p in discovery.claude_session_files(claude)]
        codex, self.zst_ignored = discovery.codex_session_files(discovery.codex_roots(self.env), discovery.zstd_bin(self.env))
        out += [("codex", p) for p in codex]
        self.index.set_subagents(discovery.claude_subagent_counts(claude))
        return out

    def scan(self) -> int:
        """Agenda a leitura dos arquivos novos ou alterados. Devolve quantos foram agendados."""
        if not self._seen:
            self._seen = self.index.known()
        scheduled = 0
        current = set()
        for agent, path in self.files():
            key = str(path)
            current.add(key)
            try:
                st = path.stat()
            except OSError:
                continue
            sig = (st.st_mtime, st.st_size)
            if self._seen.get(key) == sig and key not in self._pending:
                continue
            if self._seen.get(key) != sig:
                self._seen[key] = sig
                debouncer = self._pending.get(key)
                if debouncer is None:
                    debouncer = Debouncer(self.debounce, self._reader(agent, key), clock=self.clock)
                    self._pending[key] = debouncer
                debouncer.touch()
                scheduled += 1
        for key in [k for k in self._seen if k not in current and k not in self._pending]:
            del self._seen[key]  # removed or archived file: does not stay in memory forever
        self.last_scan = time.time()
        return scheduled

    def _reader(self, agent: str, key: str) -> Callable[[], None]:
        def read() -> None:
            self._reading += 1
            self._pending.pop(key, None)
            try:
                changed = self.index.update_file(agent, key)
            except Exception as exc:  # noqa: BLE001  forget the signature: the next scan tries again
                self._seen.pop(key, None)
                self._error(f"{Path(key).name}: {type(exc).__name__}: {exc}")
                return
            finally:
                self._reading -= 1
            if changed:
                self._changed.append(changed)
        return read

    def settled(self) -> bool:
        """Has scanned at least once and no file is waiting to be read or being read."""
        return self.last_scan is not None and not self._pending and not self._reading

    def poll(self, flush: bool = False) -> List[str]:
        """Reads the files whose deadline expired (all, with flush). Returns the ids that changed."""
        for debouncer in list(self._pending.values()):
            if self._stop.is_set():
                break  # shutting down: do not start another file
            debouncer.flush() if flush else debouncer.poll()
        changed, self._changed = self._changed, []
        if changed and self.on_change:
            self.on_change(changed)
        return changed

    def run_once(self) -> List[str]:
        with self._lock:
            self.scan()
            return self.poll(flush=True)

    def _error(self, message: str) -> None:
        """Keeps the error in memory (API) and in the index (--doctor, which runs in another process)."""
        self.last_error = message
        try:
            self.index.note_error(message)
        except Exception:  # noqa: BLE001  the index may be closing
            pass

    # ── thread ─────────────────────────────────────────────────────────────
    def start(self) -> "AgentWatcher":
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="agent-watcher", daemon=True)
            self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        next_scan = 0.0
        while not self._stop.is_set():
            try:
                with self._lock:
                    if self.clock() >= next_scan:
                        self.scan()
                        next_scan = self.clock() + self.interval
                    self.poll()
            except Exception as exc:  # noqa: BLE001  one bad file must not bring down the watching
                self._error(f"{type(exc).__name__}: {exc}")
            self._stop.wait(0.1)
