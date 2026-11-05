"""Who is using the data folder. Every running instance holds a shared lock; a restore needs it alone. The system frees the lock when a
process ends, however it ends, so a crash leaves nothing behind."""

from __future__ import annotations

import os
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: no shared lock here, and the restore goes on without waiting
    fcntl = None

LOCK_NAME = ".app.lock"
STEP = 0.1


class DataLock:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / LOCK_NAME
        self.fd = None

    def _open(self) -> bool:
        if fcntl is None:
            return False
        if self.fd is None:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
            except OSError:
                return False
        return True

    def share(self) -> None:
        """From now until the end of this process, the folder is in use."""
        if self._open():
            try:
                fcntl.flock(self.fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except OSError:
                pass  # another instance is restoring right now: this one does not get in the way

    def alone(self, seconds: float) -> bool:
        """Waits for the other instances to leave. True if this one is alone, or if the system has no lock to ask."""
        if not self._open():
            return fcntl is None
        deadline = time.monotonic() + seconds
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except OSError:
                if time.monotonic() >= deadline:
                    return False
                time.sleep(STEP)

    def release(self) -> None:
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
