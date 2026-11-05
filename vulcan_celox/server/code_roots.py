"""Which folders the Code screen may open: the known ones and those the user chose. Removing one only takes it off the list."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from vulcan_celox.server.fs_api import expand, home_dir, short
from vulcan_celox.server.known_roots import known_folders, touches_agent_data
from vulcan_celox.server.local_http import HttpError

MAX_CHOSEN = 50
KNOWN_TTL = 10.0
STORE = "code_roots"
REFUSALS = {
    "agent_data": "esta pasta contém os dados dos agentes e não pode ser aberta",
    "home": "a pasta pessoal inteira não pode ser aberta: escolha uma pasta de projeto",
    "disk": "a raiz do disco não pode ser aberta: escolha uma pasta de projeto",
    "app_data": "esta pasta contém os dados do Vulcan Celox e não pode ser aberta",
}


class CodeRoots:
    def __init__(self, app):
        self.app = app
        self.lock = threading.Lock()
        self.write_lock = threading.Lock()  # two requests at once must not lose a folder
        self.known_at = -KNOWN_TTL
        self.known_cache: List[str] = []

    def chosen(self) -> List[str]:
        data = self.app.store.load(STORE, [])
        return [p for p in data if isinstance(p, str)] if isinstance(data, list) else []

    def known(self) -> List[str]:
        """Sites and the session index do not change every second, and the screen asks every second."""
        now = time.monotonic()
        with self.lock:
            if now - self.known_at < KNOWN_TTL:
                return self.known_cache
        folders = known_folders(self.app)
        with self.lock:
            self.known_cache, self.known_at = folders, now
        return folders

    def refusal(self, path: str) -> Optional[str]:
        """The reason this folder can never be a root, or None."""
        try:
            real = Path(path).resolve()
            home = Path(home_dir(self.app.env)).resolve()
            data = Path(self.app.data_dir).resolve()
        except (OSError, RuntimeError, ValueError):
            return "disk"
        if real == Path(real.anchor) or str(real) == real.anchor:
            return "disk"
        if real == home or home.is_relative_to(real):
            return "home"
        if real == data or data.is_relative_to(real) or real.is_relative_to(data):
            return "app_data"
        if touches_agent_data(str(real), self.app.env):
            return "agent_data"
        return None

    def allowed(self, root: Optional[str]) -> str:
        """Real path of a root the user may read, or a 403 with the reason."""
        if not root or "\x00" in root or not os.path.isabs(root):
            raise HttpError(403, "pasta não permitida", {"reason": "root_refused"})
        reason = self.refusal(root)
        if reason:
            raise HttpError(403, REFUSALS[reason], {"reason": "root_refused", "why": reason})
        real = str(Path(root).resolve())
        for path in [*self.chosen(), *self.known()]:
            try:
                if str(Path(path).resolve()) == real:
                    return real
            except (OSError, RuntimeError, ValueError):
                continue
        raise HttpError(403, "pasta não permitida", {"reason": "root_refused"})

    def _sources(self) -> List[Tuple[str, str]]:
        out: List[Tuple[str, str]] = []
        node = getattr(self.app, "node", None)
        out += [(p, "chosen") for p in self.chosen()]
        out += [(s.path, "site") for s in self.app.sites() if s.path]
        if node is not None:
            out += [(p, "node") for p in node.saved().values()]
        out += [(p, "session") for p in self.known()]
        return out

    def listing(self) -> Dict[str, Any]:
        """Each folder once, with the strongest origin. A known folder that no longer exists does not appear; a chosen one does, so it can be removed."""
        seen: Dict[str, Dict[str, Any]] = {}
        chosen = {str(Path(p).resolve()) for p in self.chosen()}
        for path, source in self._sources():
            try:
                real = str(Path(path).resolve())
            except (OSError, RuntimeError, ValueError):
                continue
            exists = os.path.isdir(real)
            if real in seen or self.refusal(real) or (not exists and source != "chosen"):
                continue
            seen[real] = {"path": real, "name": os.path.basename(real) or real, "short": short(real, self.app.env),
                          "source": source, "exists": exists, "removable": real in chosen}
        order = {"chosen": 0, "site": 1, "node": 2, "session": 3}
        roots = sorted(seen.values(), key=lambda r: (order[r["source"]], r["name"].casefold(), r["path"]))
        return {"roots": roots, "max_chosen": MAX_CHOSEN}

    def add(self, raw: Any) -> Dict[str, Any]:
        if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
            raise HttpError(400, "path deve ser o caminho de uma pasta", {"reason": "invalid"})
        path = expand(raw, self.app.env)
        real = path.resolve() if path.exists() else path
        if not path.is_dir():
            raise HttpError(400, "pasta não encontrada", {"reason": "missing"})
        reason = self.refusal(str(real))
        if reason:
            raise HttpError(403, REFUSALS[reason], {"reason": "root_refused", "why": reason})
        with self.write_lock:
            chosen = self.chosen()
            if str(real) not in chosen:
                if len(chosen) >= MAX_CHOSEN:
                    raise HttpError(400, "limite de pastas escolhidas: remova uma da lista", {"reason": "limit"})
                self.app.store.save(STORE, [*chosen, str(real)])
        return {**self.listing(), "added": str(real)}

    def remove(self, raw: Optional[str]) -> Dict[str, Any]:
        if not raw:
            raise HttpError(400, "path deve ser o caminho de uma pasta", {"reason": "invalid"})
        real = os.path.realpath(raw)
        with self.write_lock:
            left = [p for p in self.chosen() if p != raw and os.path.realpath(p) != real]
            self.app.store.save(STORE, left)
        return self.listing()
