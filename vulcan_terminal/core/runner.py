"""Execução de processos: único módulo do pacote que usa subprocess (D5)."""

from __future__ import annotations

import fcntl
import os
import signal
import struct
import subprocess
import termios
import threading
import time
import warnings
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from vulcan_terminal.core.oscompat import default_shell

SHELL = default_shell()  # zsh no macOS; no Linux, $SHELL ou o que existir
KILL_GRACE_SECONDS = 3.0


@dataclass
class Result:
    code: int
    stdout: str = ""
    stderr: str = ""
    duration: float = 0.0
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def output(self) -> str:
        return (self.stdout or "") + (self.stderr or "")


def _kill_group(proc: subprocess.Popen, sig: int) -> None:
    try:
        os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _terminate(proc: subprocess.Popen) -> None:
    """SIGTERM no grupo e SIGKILL se não sair em KILL_GRACE_SECONDS."""
    if proc.poll() is not None:
        return
    _kill_group(proc, signal.SIGTERM)
    try:
        proc.wait(timeout=KILL_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        _kill_group(proc, signal.SIGKILL)
        proc.wait()


class Handle:
    """Processo em streaming."""

    def __init__(self, proc: Optional[subprocess.Popen], reader: Optional[threading.Thread]):
        self._proc = proc
        self._reader = reader
        self.cancelled = False

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def cancel(self) -> None:
        self.cancelled = True
        if self._proc is not None:
            _terminate(self._proc)

    def wait(self, timeout: Optional[float] = None) -> bool:
        """True se terminou (inclusive a entrega de todas as linhas)."""
        if self._reader is None:
            return True
        self._reader.join(timeout)
        return not self._reader.is_alive()


class Runner:
    def run(self, argv: Sequence[str], cwd: Optional[str] = None,
            env: Optional[Mapping[str, str]] = None, timeout: float = 60.0, input: Optional[str] = None) -> Result:
        """`input` vai pelo stdin (nunca pela linha de comando, que outros processos enxergam)."""
        start = time.monotonic()
        try:
            proc = subprocess.Popen(list(argv), cwd=cwd, env=dict(env) if env is not None else None,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                                    text=True, start_new_session=True)
        except FileNotFoundError as exc:
            return Result(127, "", str(exc), time.monotonic() - start)
        except PermissionError as exc:
            return Result(126, "", str(exc), time.monotonic() - start)
        try:
            out, err = proc.communicate(input=input, timeout=timeout)
        except subprocess.TimeoutExpired:
            _terminate(proc)
            out, err = proc.communicate()
            return Result(-1, out or "", err or "", time.monotonic() - start, timed_out=True)
        return Result(proc.returncode, out or "", err or "", time.monotonic() - start)

    def run_shell(self, cmdline: str, cwd: Optional[str] = None,
                  env: Optional[Mapping[str, str]] = None, timeout: float = 60.0) -> Result:
        return self.run([SHELL, "-lc", cmdline], cwd=cwd, env=env, timeout=timeout)

    def stream(self, argv: Sequence[str], cwd: Optional[str] = None,
               env: Optional[Mapping[str, str]] = None,
               on_line: Callable[[str], None] = lambda _l: None,
               on_exit: Callable[[int], None] = lambda _c: None) -> Handle:
        """Executa em segundo plano entregando stdout+stderr linha a linha.

        Os callbacks rodam na thread leitora: a UI deve repassá-los por fila.
        """
        try:
            proc = subprocess.Popen(list(argv), cwd=cwd, env=dict(env) if env is not None else None,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, text=True, bufsize=1,
                                    start_new_session=True)
        except (FileNotFoundError, PermissionError) as exc:
            on_line(f"erro: {exc}")
            on_exit(127 if isinstance(exc, FileNotFoundError) else 126)
            return Handle(None, None)

        def _read():
            assert proc.stdout is not None
            for line in proc.stdout:
                on_line(line.rstrip("\n"))
            proc.stdout.close()
            on_exit(proc.wait())

        reader = threading.Thread(target=_read, name="vulcan-stream", daemon=True)
        reader.start()
        return Handle(proc, reader)

    def stream_shell(self, cmdline: str, cwd: Optional[str] = None,
                     env: Optional[Mapping[str, str]] = None,
                     on_line: Callable[[str], None] = lambda _l: None,
                     on_exit: Callable[[int], None] = lambda _c: None) -> Handle:
        return self.stream([SHELL, "-lc", cmdline], cwd=cwd, env=env, on_line=on_line, on_exit=on_exit)


def open_pipe(argv: Sequence[str]) -> subprocess.Popen:
    """Saída de um comando em stream, sem guardar tudo na memória. Levanta OSError se não rodar."""
    return subprocess.Popen(list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            start_new_session=True)


def close_pipe(proc: subprocess.Popen, grace: float = 5.0) -> Optional[int]:
    """Fecha a saída e espera o processo; se não sair em `grace` segundos, encerra. Devolve o código de saída."""
    proc.stdout.close()
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        _terminate(proc)
    return proc.returncode


# ── pseudo-terminal ──────────────────────────────────────────────────────────
def set_winsize(fd: int, rows: int, cols: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", max(1, rows), max(1, cols), 0, 0))


def spawn_pty(argv: Sequence[str], cwd: Optional[str], env: Mapping[str, str],
              rows: int = 24, cols: int = 80) -> Tuple[int, int]:
    """Processo com terminal controlador próprio (forkpty). Retorna (pid, fd do mestre).

    O filho só faz chdir e exec, então o fork a partir de um processo com threads é seguro.
    """
    argv = list(argv)
    env = dict(env)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)  # aviso de fork com threads (Python 3.12+)
        pid, fd = os.forkpty()
    if pid == 0:  # filho
        try:
            if cwd:
                os.chdir(cwd)
            os.execvpe(argv[0], argv, env)
        finally:
            os._exit(127)
    try:
        set_winsize(fd, rows, cols)
    except Exception:  # tamanho recusado: não deixa shell órfão nem fd aberto
        try:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        except OSError:
            pass
        os.close(fd)
        raise
    return pid, fd


def terminate_pty(pid: int, grace: float = 2.0) -> Optional[int]:
    """SIGHUP no grupo do terminal, SIGKILL se não sair em `grace` segundos. Retorna o status."""
    for sig in (signal.SIGHUP, signal.SIGTERM):
        try:
            os.killpg(pid, sig)
        except (ProcessLookupError, PermissionError):
            pass
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        try:
            done, status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return None
        if done:
            return status
        time.sleep(0.05)
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        return os.waitpid(pid, 0)[1]
    except ChildProcessError:
        return None


def terminate_many(pids: Sequence[int], grace: float = 2.0) -> Dict[int, Optional[int]]:
    """Como terminate_pty para várias abas de uma vez: sinal para todas, uma espera só.
    Dez abas que ignoram SIGHUP levam `grace` segundos, não dez vezes isso."""
    for pid in pids:
        for sig in (signal.SIGHUP, signal.SIGTERM):
            try:
                os.killpg(pid, sig)
            except (ProcessLookupError, PermissionError):
                pass
    statuses: Dict[int, Optional[int]] = {}
    pending = set(pids)
    deadline = time.monotonic() + grace
    while pending and time.monotonic() < deadline:
        for pid in list(pending):
            try:
                done, status = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                statuses[pid] = None
                pending.discard(pid)
                continue
            if done:
                statuses[pid] = status
                pending.discard(pid)
        if pending:
            time.sleep(0.05)
    for pid in pending:
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            statuses[pid] = os.waitpid(pid, 0)[1]
        except ChildProcessError:
            statuses[pid] = None
    return statuses


# ── duplo para testes ────────────────────────────────────────────────────────
@dataclass
class Call:
    argv: Tuple[str, ...]
    cwd: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    input: Optional[str] = None


class FakeHandle(Handle):
    def __init__(self):
        super().__init__(None, None)
        self.cancel_calls = 0

    def cancel(self) -> None:
        self.cancelled = True
        self.cancel_calls += 1


@dataclass
class FakeRunner:
    """Registra chamadas e devolve respostas programadas por argv."""

    responses: Dict[Tuple[str, ...], Result] = field(default_factory=dict)
    default: Result = field(default_factory=lambda: Result(0))
    calls: List[Call] = field(default_factory=list)
    handles: List[FakeHandle] = field(default_factory=list)

    def respond(self, argv: Sequence[str], result: Result) -> None:
        self.responses[tuple(argv)] = result

    def run(self, argv, cwd=None, env=None, timeout=60.0, input=None) -> Result:
        self.calls.append(Call(tuple(argv), cwd, dict(env) if env else None, input))
        return self.responses.get(tuple(argv), self.default)

    def run_shell(self, cmdline, cwd=None, env=None, timeout=60.0) -> Result:
        return self.run([SHELL, "-lc", cmdline], cwd=cwd, env=env, timeout=timeout)

    def stream(self, argv, cwd=None, env=None, on_line=lambda _l: None, on_exit=lambda _c: None):
        result = self.run(argv, cwd=cwd, env=env)
        for line in result.output.splitlines():
            on_line(line)
        on_exit(result.code)
        handle = FakeHandle()
        self.handles.append(handle)
        return handle

    def stream_shell(self, cmdline, cwd=None, env=None, on_line=lambda _l: None,
                     on_exit=lambda _c: None):
        return self.stream([SHELL, "-lc", cmdline], cwd=cwd, env=env, on_line=on_line, on_exit=on_exit)
