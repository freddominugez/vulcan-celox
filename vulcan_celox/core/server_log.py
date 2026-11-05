"""Server log on disk: what the server did, and what it wrote on its way down. Every line goes through the mask
first, and the session token never reaches the file."""

from __future__ import annotations

import io
import logging
import logging.handlers
import os
import threading
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from vulcan_celox.core.redact import redact

LOG_DIR = "logs"
LOG_FILE = "servidor.log"
ERR_FILE = "servidor-erro.log"
MAX_BYTES = 1024 * 1024
BACKUPS = 3
TAIL_LINES = 20
TOKEN_MASK = "[token]"
LOGGER = "vulcan_celox.server"

_logger = logging.getLogger(LOGGER)
_logger.addHandler(logging.NullHandler())  # tests and the tkinter fallback write nothing and print nothing
_logger.propagate = False


def logger() -> logging.Logger:
    return _logger


def log_paths(data_dir) -> Tuple[Path, Path]:
    folder = Path(data_dir) / LOG_DIR
    return folder / LOG_FILE, folder / ERR_FILE


def _private(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def mask(text: str, secrets: Iterable[str] = ()) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, TOKEN_MASK)
    return redact(text)[0]


class MaskingFormatter(logging.Formatter):
    def __init__(self, secrets: Iterable[str] = ()):
        super().__init__("%(asctime)s %(levelname)s %(message)s")
        self.secrets = tuple(s for s in secrets if s)

    def format(self, record: logging.LogRecord) -> str:
        return mask(super().format(record), self.secrets)


class PrivateRotatingHandler(logging.handlers.RotatingFileHandler):
    """Each file, including the ones a rotation creates, is readable by the user only."""

    def _open(self):
        stream = super()._open()
        _private(Path(self.baseFilename))
        return stream


def setup(data_dir, secrets: Iterable[str] = (), max_bytes: int = MAX_BYTES, backups: int = BACKUPS) -> logging.Logger:
    """Sends the server log to `<data>/logs/servidor.log`. Called once by the process that serves."""
    path, _err = log_paths(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    for old in [h for h in _logger.handlers if isinstance(h, PrivateRotatingHandler)]:
        _logger.removeHandler(old)
        old.close()
    handler = PrivateRotatingHandler(str(path), maxBytes=max_bytes, backupCount=backups, encoding="utf-8")
    handler.setFormatter(MaskingFormatter(secrets))
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)
    return _logger


def start_serving(data_dir, token: str) -> logging.Logger:
    """For the process the native shell started: its error output already goes to the error log, and what Python
    writes there leaves masked."""
    import sys
    sys.stderr = MaskedStream(sys.stderr, [token])
    return setup(data_dir, [token])


def close() -> None:
    for handler in [h for h in _logger.handlers if isinstance(h, PrivateRotatingHandler)]:
        _logger.removeHandler(handler)
        handler.close()


def prepare_error_log(data_dir, limit: int = MAX_BYTES) -> Path:
    """The file that receives the server's error output. Starts over when it grew past the limit."""
    _path, err = log_paths(data_dir)
    err.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(err.parent, 0o700)
    try:
        if err.stat().st_size > limit:
            err.write_bytes(b"")
    except FileNotFoundError:
        err.touch()
    _private(err)
    return err


def redirect_stderr(data_dir, secrets: Iterable[str] = ()) -> Optional[Path]:
    """Points the process error output (file descriptor 2) at the error log, for shells that serve in-process.
    A traceback that kills the process lands there even without the logging module."""
    try:
        err = prepare_error_log(data_dir)
        fd = os.open(str(err), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        os.dup2(fd, 2)
        os.close(fd)
    except OSError:
        return None
    import sys
    sys.stderr = MaskedStream(io.TextIOWrapper(io.FileIO(2, "w", closefd=False), encoding="utf-8", line_buffering=True),
                              secrets)
    return err


class MaskedStream:
    """Text stream that masks each line before passing it on (Python's own tracebacks included)."""

    def __init__(self, target, secrets: Iterable[str] = ()):
        self.target = target
        self.secrets = tuple(s for s in secrets if s)
        self._pending = ""
        self._lock = threading.Lock()

    def write(self, text: str) -> int:
        with self._lock:
            self._pending += text
            if "\n" in self._pending:
                done, self._pending = self._pending.rsplit("\n", 1)
                self.target.write(mask(done + "\n", self.secrets))
                self.target.flush()
        return len(text)

    def flush(self) -> None:
        with self._lock:
            if self._pending:
                self.target.write(mask(self._pending, self.secrets))
                self._pending = ""
            self.target.flush()

    def fileno(self) -> int:
        return self.target.fileno()

    def isatty(self) -> bool:
        return False


def tail(path, lines: int = TAIL_LINES, secrets: Iterable[str] = (), window: int = 64 * 1024) -> List[str]:
    """The last lines of a log, masked again: the file may hold what an older version wrote unmasked."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - window))
            data = fh.read()
    except OSError:
        return []
    text = data.decode("utf-8", "replace")
    if size > window:
        text = text.split("\n", 1)[-1]  # the first line was cut by the window
    kept = [line for line in text.splitlines() if line.strip()][-lines:]
    return mask("\n".join(kept), secrets).splitlines() if kept else []
