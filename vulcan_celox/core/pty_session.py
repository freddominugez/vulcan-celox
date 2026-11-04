"""Real terminal sessions (PTY) with history for reconnection."""

from __future__ import annotations

import os
import select
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence

from vulcan_celox.core import procinfo
from vulcan_celox.core.quick_commands import is_long_running
from vulcan_celox.core.runner import WINDOWS, set_winsize, spawn_pty, terminate_many, terminate_pty

HISTORY_LIMIT = 256 * 1024
READ_CHUNK = 65536
WRITE_TIMEOUT = 5.0  # seconds without the tab reading anything: the write gives up

Listener = Callable[[Optional[bytes]], None]  # None = processo terminou


class PtySession:
    def __init__(self, argv: Sequence[str], cwd: str, env: Mapping[str, str], title: str = "",
                 site: Optional[str] = None, rows: int = 24, cols: int = 80, session_id: Optional[str] = None,
                 theme: Optional[str] = None, command: Optional[str] = None):
        self.id = session_id or new_session_id()
        self.command = command  # initial command of the tab (None = just the shell)
        self.theme = theme
        self.argv = list(argv)
        self.cwd = cwd
        self.title = title or Path(cwd).name or "terminal"
        self.site = site
        self.created_at = time.time()
        self.rows, self.cols = rows, cols
        self.exit_code: Optional[int] = None
        self._history = bytearray()
        self._listeners: List[Listener] = []
        self._lock = threading.Lock()
        self.ended = False  # the reader already delivered the end of the process to the listeners it had
        self.pid, handle = spawn_pty(self.argv, cwd, env, rows, cols)
        self._win = handle if WINDOWS else None  # on Windows the terminal is a ConPTY object, with two descriptors
        self.fd = self._win.read_fd if WINDOWS else handle
        # non-blocking master and one write at a time. A large paste does not mix with the WebSocket
        # keystrokes, and a tab that does not read its input does not hold the writing thread.
        if not WINDOWS:
            os.set_blocking(self.fd, False)
        self._write_lock = threading.Lock()
        self._closed = False
        # self-pipe: close() wakes the reader thread, which is the only one to close the PTY fd. Closing the fd
        # from another thread left the number free for another tab while the reader could still read from it.
        self._wake_r, self._wake_w = os.pipe()
        self._fds_closed = False
        self._reader = threading.Thread(target=self._read_loop, name=f"pty-{self.id}", daemon=True)
        self._reader.start()

    @property
    def alive(self) -> bool:
        return self.exit_code is None and not self._closed

    # ── E/S ──────────────────────────────────────────────────────────────
    def _read_loop(self) -> None:
        try:
            self._pump()
        finally:
            self._reap()
            with self._lock:
                self.ended = True  # whoever subscribes from here on does not receive the end: see `ended`
                listeners = list(self._listeners)
            for listener in listeners:
                try:
                    listener(None)
                except Exception:  # noqa: BLE001
                    pass
            self._close_fds()  # also when the process exits on its own

    def _pump(self) -> None:
        while True:
            try:
                if not WINDOWS:  # on Windows select does not work for pipes: the read blocks until the console closes
                    ready, _, _ = select.select([self.fd, self._wake_r], [], [], 0.5)
                    if self._wake_r in ready or (not ready and self._closed):
                        break
                    if not ready:
                        continue
                chunk = os.read(self.fd, READ_CHUNK)
            except BlockingIOError:
                continue  # select acordou sem dado de verdade
            except (OSError, ValueError):
                break
            if not chunk:
                break
            with self._lock:
                self._history.extend(chunk)
                if len(self._history) > HISTORY_LIMIT:
                    del self._history[: len(self._history) - HISTORY_LIMIT]
                listeners = list(self._listeners)
            for listener in listeners:
                try:
                    listener(chunk)
                except Exception:  # noqa: BLE001 (a misbehaving client does not bring down the session)
                    self.unsubscribe(listener)

    def _close_fds(self) -> None:
        with self._lock:
            if self._fds_closed:
                return
            self._fds_closed = True
        with self._write_lock:  # the writer sees _fds_closed and leaves; the fd number does not become free in the middle of a write
            pass
        if self._win is not None:
            self._win.release()
        for fd in ((self._wake_r, self._wake_w) if WINDOWS else (self.fd, self._wake_r, self._wake_w)):
            try:
                os.close(fd)
            except OSError:
                pass

    def _reap(self) -> None:
        if self.exit_code is not None:
            return
        if self._win is not None:
            self.exit_code = self._win.wait()
            return
        try:
            done, status = os.waitpid(self.pid, 0)
            self.exit_code = os.waitstatus_to_exitcode(status) if hasattr(os, "waitstatus_to_exitcode") \
                else (status >> 8)
        except ChildProcessError:
            self.exit_code = self.exit_code if self.exit_code is not None else -1

    def write(self, data: bytes, timeout: float = WRITE_TIMEOUT) -> bool:
        """Writes everything or gives up after `timeout` seconds without the tab reading anything. True only if everything was written."""
        with self._write_lock:
            view = memoryview(data)
            deadline = time.monotonic() + timeout
            if self._win is not None:  # pipe do console: escrita bloqueante
                try:
                    while view and self.alive and not self._fds_closed:
                        view = view[self._win.write(view[:4096]):]
                except OSError:
                    return False
                return not view
            while view:
                if not self.alive or self._fds_closed:
                    return False
                try:
                    written = os.write(self.fd, view)
                except BlockingIOError:
                    written = 0
                except OSError:
                    return False
                if written:
                    view = view[written:]
                    deadline = time.monotonic() + timeout  # the deadline counts only the stalled time
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                try:
                    select.select([], [self.fd], [], min(remaining, 0.25))
                except (OSError, ValueError):
                    return False
            return True

    def foreground(self) -> Optional[List[procinfo.Proc]]:
        """Foreground group processes of the tab; None when it cannot be known."""
        if not self.alive or self._fds_closed or self._win is not None:  # Windows has no foreground group
            return None
        return procinfo.group_processes(procinfo.foreground_pgid(self.fd))

    def resize(self, rows: int, cols: int) -> None:
        self.rows, self.cols = int(rows), int(cols)
        if self.alive:
            try:
                if self._win is not None:
                    self._win.resize(self.rows, self.cols)
                else:
                    set_winsize(self.fd, self.rows, self.cols)
            except OSError:
                pass

    def subscribe(self, listener: Listener, prime: Optional[Callable[[bytes], None]] = None) -> bytes:
        """Registers the listener and returns the current history, without losing bytes between the two. `prime` receives the history
                inside the lock: whatever it enqueues comes before any new block delivered to the listener."""
        with self._lock:
            self._listeners.append(listener)
            history = bytes(self._history)
            if prime is not None:
                prime(history)
            return history

    def unsubscribe(self, listener: Listener) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def history(self) -> bytes:
        with self._lock:
            return bytes(self._history)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._finish_close(terminate_pty(self.pid) if self.exit_code is None else None)

    def _finish_close(self, status: Optional[int]) -> None:
        """After the process ends: records the code, wakes the reader and waits for it to close the fd."""
        self._closed = True
        if self.exit_code is None:
            if status is not None:
                self.exit_code = os.waitstatus_to_exitcode(status) if hasattr(os, "waitstatus_to_exitcode") \
                    else (status >> 8)
            if self.exit_code is None:
                self.exit_code = -1
        if self._win is not None:
            self._win.close_console()  # this is what ends the blocking read
        with self._lock:
            wake = not self._fds_closed
        if wake:
            try:
                os.write(self._wake_w, b"x")
            except OSError:
                pass
        if threading.current_thread() is not self._reader:
            self._reader.join(timeout=5)
        self._close_fds()

    def info(self) -> Dict:
        return {"id": self.id, "title": self.title, "site": self.site, "cwd": self.cwd, "argv": self.argv,
                "alive": self.alive, "exit_code": self.exit_code, "rows": self.rows, "cols": self.cols,
                "created_at": self.created_at, "theme": self.theme, "command": self.command,
                "long_running": is_long_running(self.command)}


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]


def terminal_env(base: Mapping[str, str]) -> Dict[str, str]:
    env = dict(base)
    home = env.get("HOME") or str(Path.home())
    if not WINDOWS:
        extra = [str(Path(home) / ".local" / "share" / "lerd" / "bin"), str(Path(home) / ".local" / "bin"),
                 "/opt/homebrew/bin", "/usr/local/bin"]
        current = [p for p in env.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin").split(":") if p]
        env["PATH"] = ":".join(extra + [p for p in current if p not in extra])
    env["TERM"] = "xterm-256color"
    env["COLORTERM"] = "truecolor"
    env["TERM_PROGRAM"] = "VulcanCelox"
    env.setdefault("LANG", "pt_BR.UTF-8")
    for key in ("VULCAN_TOKEN", "VULCAN_WATCH_PARENT"):
        env.pop(key, None)  # the server's token never leaks into the user's shell
    return env


class TerminalManager:
    def __init__(self, base_env: Mapping[str, str]):
        self.base_env = dict(base_env)
        self._sessions: Dict[str, PtySession] = {}
        self._lock = threading.Lock()

    def shell(self) -> str:
        from vulcan_celox.core.oscompat import default_shell
        return default_shell(self.base_env)

    def argv_for(self, command: Optional[str]) -> List[str]:
        from vulcan_celox.core.oscompat import interactive_argv
        return interactive_argv(self.shell(), command)

    def create(self, cwd: str, command: Optional[str] = None, title: str = "", site: Optional[str] = None,
               rows: int = 24, cols: int = 80, theme: Optional[str] = None) -> PtySession:
        session_id = new_session_id()  # before the process is born: the id goes into the shell's environment
        env = terminal_env(self.base_env)
        # pareamento: o Claude Code ou o Codex iniciado nesta aba herda o id dela e o tema
        env["VULCAN_SESSION_ID"] = session_id
        if theme:
            env["VULCAN_THEME"] = theme
        else:
            env.pop("VULCAN_THEME", None)
        title = self.unique_title(title or Path(cwd).name or "terminal")
        session = PtySession(self.argv_for(command), cwd, env, title=title, site=site, rows=rows, cols=cols,
                             session_id=session_id, theme=theme, command=command)
        with self._lock:
            self._sessions[session.id] = session
        return session

    def unique_title(self, title: str) -> str:
        """'loja', 'loja 2', 'loja 3'... among the open sessions."""
        taken = {s.title for s in self.list()}
        if title not in taken:
            return title
        n = 2
        while f"{title} {n}" in taken:
            n += 1
        return f"{title} {n}"

    def get(self, session_id: str) -> Optional[PtySession]:
        with self._lock:
            return self._sessions.get(session_id)

    def list(self) -> List[PtySession]:
        with self._lock:
            return sorted(self._sessions.values(), key=lambda s: s.created_at)

    def close(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        session.close()
        return True

    def close_all(self) -> None:
        """Ends all tabs together: a signal to all and a single wait."""
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        alive = [s for s in sessions if not s._closed and s.exit_code is None]
        for s in sessions:
            s._closed = True
        statuses = terminate_many([s.pid for s in alive])
        for s in sessions:
            s._finish_close(statuses.get(s.pid))
