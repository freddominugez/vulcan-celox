"""Modo local: sem Lerd nem Valet. Notas, tags, tarefas e sites manuais continuam funcionando."""

from __future__ import annotations

from vulcan_terminal.core.backends.base import Backend
from vulcan_terminal.core.runner import Result

MESSAGE = ("Nenhum ambiente encontrado. Instale o Lerd (https://lerd.sh) ou o Laravel Valet:\n"
           "composer global require laravel/valet && valet install")


class NullBackend(Backend):
    name = "local"
    label = "modo local (sem Lerd ou Valet)"
    available = False

    def _unavailable(self) -> Result:
        return Result(1, "", MESSAGE)

    def start(self) -> Result:
        return self._unavailable()

    def stop(self) -> Result:
        return self._unavailable()

    def restart(self) -> Result:
        return self._unavailable()

    def share_argv(self, name, tool=None):
        raise NotImplementedError(MESSAGE)
