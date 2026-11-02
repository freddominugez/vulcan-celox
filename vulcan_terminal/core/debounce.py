"""Debounce com relógio injetável: a UI chama touch() a cada mudança e poll() periodicamente."""

from __future__ import annotations

import time
from typing import Callable, Optional


class Debouncer:
    def __init__(self, delay: float, action: Callable[[], None],
                 clock: Callable[[], float] = time.monotonic):
        self.delay = delay
        self.action = action
        self.clock = clock
        self._due: Optional[float] = None

    @property
    def pending(self) -> bool:
        return self._due is not None

    def touch(self) -> None:
        self._due = self.clock() + self.delay

    def poll(self) -> bool:
        """Executa a ação se o prazo venceu. Retorna True se executou."""
        if self._due is not None and self.clock() >= self._due:
            self._due = None
            self.action()
            return True
        return False

    def flush(self) -> bool:
        if self._due is None:
            return False
        self._due = None
        self.action()
        return True
