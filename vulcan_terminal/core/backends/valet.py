"""Backend Laravel Valet (MIT): chama a CLI `valet`."""

from __future__ import annotations

from typing import List, Optional, Tuple

from vulcan_terminal.core.backends.base import Backend
from vulcan_terminal.core.runner import Result

SERVICE_TIMEOUT = 120.0


class ValetBackend(Backend):
    name = "valet"
    label = "Laravel Valet"
    available = True

    def argv(self, *args: str) -> List[str]:
        return [str(self.bin_path), *args]

    def start(self) -> Result:
        return self.runner.run(self.argv("start"), timeout=SERVICE_TIMEOUT)

    def stop(self) -> Result:
        return self.runner.run(self.argv("stop"), timeout=SERVICE_TIMEOUT)

    def restart(self) -> Result:
        return self.runner.run(self.argv("restart"), timeout=SERVICE_TIMEOUT)

    # ── ações de site (vt-02 C1) ─────────────────────────────────────────
    def site_command(self, action: str, *args: str) -> Tuple[List[str], Optional[str]]:
        if action == "link":
            path, domain = args
            return self.argv("link", *([domain] if domain else [])), path
        if action == "park":
            return self.argv("park"), args[0]
        if action == "unpark":
            return self.argv("forget"), args[0]  # forget é o equivalente do unpark no Valet (D-013)
        if action == "isolate":
            _path, php, name = args
            return self.argv("isolate", f"php@{php}", f"--site={name}"), None
        if action == "isolate_node":
            raise NotImplementedError("o Valet não isola a versão de Node por site")
        if action in ("unlink", "secure", "unsecure"):
            return self.argv(action, args[0]), None
        return super().site_command(action, *args)

    def share_argv(self, name: str, tool: Optional[str] = None) -> List[str]:
        return self.argv("share")  # roda na pasta do site

    def version(self) -> str:
        r = self.runner.run(self.argv("--version"), timeout=10)
        return r.stdout.strip() if r.ok else ""
