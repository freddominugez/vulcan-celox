"""Sessões de terminal reais (PTY) com histórico para reconexão."""

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
from vulcan_celox.core.runner import set_winsize, spawn_pty, terminate_many, terminate_pty

HISTORY_LIMIT = 256 * 1024
READ_CHUNK = 65536
WRITE_TIMEOUT = 5.0  # segundos sem a aba ler nada: a escrita desiste

Listener = Callable[[Optional[bytes]], None]  # None = processo terminou


class PtySession:
    def __init__(self, argv: Sequence[str], cwd: str, env: Mapping[str, str], title: str = "",
                 site: Optional[str] = None, rows: int = 24, cols: int = 80, session_id: Optional[str] = None,
                 theme: Optional[str] = None, command: Optional[str] = None):
        self.id = session_id or new_session_id()
        self.command = command  # comando inicial da aba (None = só o shell)
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
        self.pid, self.fd = spawn_pty(self.argv, cwd, env, rows, cols)
        # Mestre não bloqueante e uma escrita por vez. Uma colagem grande não se mistura com teclas do
        # WebSocket, e uma aba que não lê a entrada não prende a thread que escreve.
        os.set_blocking(self.fd, False)
        self._write_lock = threading.Lock()
        self._closed = False
        # self-pipe: close() acorda a thread leitora, que é a única a fechar o fd do PTY. Fechar o fd
        # de outra thread deixava o número livre para outra aba enquanto o leitor ainda podia ler dele.
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
                listeners = list(self._listeners)
            for listener in listeners:
                try:
                    listener(None)
                except Exception:  # noqa: BLE001
                    pass
            self._close_fds()  # também quando o processo sai sozinho

    def _pump(self) -> None:
        while True:
            try:
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
                except Exception:  # noqa: BLE001 (um cliente com problema não derruba a sessão)
                    self.unsubscribe(listener)

    def _close_fds(self) -> None:
        with self._lock:
            if self._fds_closed:
                return
            self._fds_closed = True
        with self._write_lock:  # quem escreve vê _fds_closed e sai; o número do fd não fica livre no meio da escrita
            pass
        for fd in (self.fd, self._wake_r, self._wake_w):
            try:
                os.close(fd)
            except OSError:
                pass

    def _reap(self) -> None:
        if self.exit_code is not None:
            return
        try:
            done, status = os.waitpid(self.pid, 0)
            self.exit_code = os.waitstatus_to_exitcode(status) if hasattr(os, "waitstatus_to_exitcode") \
                else (status >> 8)
        except ChildProcessError:
            self.exit_code = self.exit_code if self.exit_code is not None else -1

    def write(self, data: bytes, timeout: float = WRITE_TIMEOUT) -> bool:
        """Escreve tudo ou desiste depois de `timeout` segundos sem a aba ler nada. True só se escreveu tudo."""
        with self._write_lock:
            view = memoryview(data)
            deadline = time.monotonic() + timeout
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
                    deadline = time.monotonic() + timeout  # o prazo conta só o tempo parado
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
        """Processos do grupo em primeiro plano da aba; None quando não dá para saber."""
        if not self.alive or self._fds_closed:
            return None
        return procinfo.group_processes(procinfo.foreground_pgid(self.fd))

    def resize(self, rows: int, cols: int) -> None:
        self.rows, self.cols = int(rows), int(cols)
        if self.alive:
            try:
                set_winsize(self.fd, self.rows, self.cols)
            except OSError:
                pass

    def subscribe(self, listener: Listener, prime: Optional[Callable[[bytes], None]] = None) -> bytes:
        """Registra o ouvinte e devolve o histórico atual, sem perder bytes entre os dois. `prime` recebe o histórico
        dentro do lock: o que ele enfileirar vem antes de qualquer bloco novo entregue ao ouvinte."""
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
        """Depois do processo encerrado: registra o código, acorda a leitora e espera ela fechar o fd."""
        self._closed = True
        if self.exit_code is None:
            if status is not None:
                self.exit_code = os.waitstatus_to_exitcode(status) if hasattr(os, "waitstatus_to_exitcode") \
                    else (status >> 8)
            if self.exit_code is None:
                self.exit_code = -1
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
    extra = [str(Path(home) / ".local" / "share" / "lerd" / "bin"), str(Path(home) / ".local" / "bin"),
             "/opt/homebrew/bin", "/usr/local/bin"]
    current = [p for p in env.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin").split(":") if p]
    env["PATH"] = ":".join(extra + [p for p in current if p not in extra])
    env["TERM"] = "xterm-256color"
    env["COLORTERM"] = "truecolor"
    env["TERM_PROGRAM"] = "VulcanCelox"
    env.setdefault("LANG", "pt_BR.UTF-8")
    for key in ("VULCAN_TOKEN", "VULCAN_WATCH_PARENT"):
        env.pop(key, None)  # o token do servidor nunca vaza para o shell do usuário
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
        shell = self.shell()
        if not command:
            return [shell, "-l"]
        # roda o comando e depois continua num shell interativo, como no Terminal.app
        return [shell, "-l", "-i", "-c", f"{command}; exec {shell} -l"]

    def create(self, cwd: str, command: Optional[str] = None, title: str = "", site: Optional[str] = None,
               rows: int = 24, cols: int = 80, theme: Optional[str] = None) -> PtySession:
        session_id = new_session_id()  # antes do processo nascer: o id vai no ambiente do shell
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
        """'loja', 'loja 2', 'loja 3'... entre as sessões abertas."""
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
        """Encerra todas as abas juntas: sinal para todas e uma espera só."""
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        alive = [s for s in sessions if not s._closed and s.exit_code is None]
        for s in sessions:
            s._closed = True
        statuses = terminate_many([s.pid for s in alive])
        for s in sessions:
            s._finish_close(statuses.get(s.pid))
