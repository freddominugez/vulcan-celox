"""Common interface of the environment backends (see docs/pt-BR/technical-manual.md section 4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from vulcan_celox.core.i18n import tr
from vulcan_celox.core.runner import Result, Runner
from vulcan_celox.core.sites import Site, discover_sites

SITE_TIMEOUT = 120.0
BUILD_TIMEOUT = 600.0  # isolate may build the image for the PHP version
NO_BACKEND = "Sem Lerd ou Valet: instale um dos dois para gerenciar sites."


@dataclass
class EnvStatus:
    running: bool
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)


class Backend:
    name = "base"
    label = "base"
    available = False

    def __init__(self, bin_path: Optional[Path] = None, runner=None,
                 valet_home: Optional[Path] = None):
        self.bin_path = Path(bin_path) if bin_path else None
        self.runner = runner if runner is not None else Runner()
        self.valet_home = valet_home

    # ── services ─────────────────────────────────────────────────────────
    def start(self) -> Result:
        raise NotImplementedError

    def stop(self) -> Result:
        raise NotImplementedError

    def restart(self) -> Result:
        raise NotImplementedError

    def nginx_running(self) -> bool:
        return self.runner.run(["/usr/bin/pgrep", "-x", "nginx"], timeout=5).code == 0

    def status(self) -> EnvStatus:
        if not self.available:
            return EnvStatus(False, self.label)
        running = self.nginx_running()
        return EnvStatus(running, tr("{label} · nginx rodando" if running else "{label} · nginx parado", label=self.label),
                         {"nginx": running})

    # ── sites ────────────────────────────────────────────────────────────
    def list_sites(self, manual: Optional[Mapping[str, str]] = None) -> List[Site]:
        return discover_sites(self.valet_home if self.available else None, manual)

    # Site actions. Each backend gives the argv and the working folder in `site_command`; the execution,
    # the validation and the "sem backend" case live here. A value that would start with a hyphen would become a CLI option: it is refused.
    def site_command(self, action: str, *args: str) -> Tuple[List[str], Optional[str]]:
        raise NotImplementedError(f"{self.label} não tem a ação {action}")

    # what the backend writes in the project folder on each action, so the interface can warn beforehand
    project_writes: Dict[str, str] = {}

    @staticmethod
    def _check(action: str, args) -> None:
        for value in args:
            if value and str(value).startswith("-"):
                raise ValueError(f"valor inválido para {action}: {value!r}")

    def site_argv(self, action: str, *args: str) -> Tuple[List[str], Optional[str]]:
        """argv and folder of an already validated action, to run in a terminal tab instead of waiting here."""
        self._check(action, args)
        return self.site_command(action, *args)

    def _site(self, action: str, *args: str, timeout: float = SITE_TIMEOUT) -> Result:
        self._check(action, args)
        if not self.available:
            return Result(1, "", NO_BACKEND)
        argv, cwd = self.site_command(action, *args)
        return self.runner.run(argv, cwd=cwd, timeout=timeout)

    def link(self, path: str, domain: str = "") -> Result:
        return self._site("link", path, domain)

    def unlink(self, name: str) -> Result:
        return self._site("unlink", name)

    def park(self, path: str) -> Result:
        return self._site("park", path)

    def unpark(self, path: str) -> Result:
        return self._site("unpark", path)

    def secure(self, name: str) -> Result:
        return self._site("secure", name)

    def unsecure(self, name: str) -> Result:
        return self._site("unsecure", name)

    def isolate(self, path: str, php: str, name: str = "") -> Result:
        return self._site("isolate", path, php, name or Path(path).name, timeout=BUILD_TIMEOUT)

    def isolate_node(self, path: str, node: str) -> Result:
        return self._site("isolate_node", path, node, timeout=BUILD_TIMEOUT)

    def share_argv(self, name: str, tool: Optional[str] = None) -> List[str]:
        raise NotImplementedError(f"{self.label} não compartilha sites")

    def php_versions(self) -> List[Dict[str, Any]]:
        """PHP versions available for the site selector: [{version, running, default}]."""
        return []
