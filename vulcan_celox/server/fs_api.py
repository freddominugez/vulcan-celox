"""Pastas para abrir terminais: validação do caminho digitado e pastas recentes (sessões e sites)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from vulcan_celox.server.local_http import HttpError, Request

RECENT_LIMIT = 12


def home_dir(env) -> str:
    return env.get("HOME") or str(Path.home())


def expand(raw: str, env) -> Path:
    raw = raw.strip()
    home = home_dir(env)
    if raw == "~" or raw.startswith("~/"):
        raw = home + raw[1:]
    return Path(os.path.abspath(raw))


def short(path: str, env) -> str:
    home = home_dir(env).rstrip("/")
    if home and (path == home or path.startswith(home + "/")):
        return "~" + path[len(home):]
    return path


def folder_info(path: Path, env, site: Optional[str] = None) -> Dict[str, Any]:
    text = str(path)
    return {"path": text, "short": short(text, env), "name": path.name or text, "exists": path.exists(),
            "is_dir": path.is_dir(), "site": site}


def register_fs_api(app) -> None:
    srv = app.server

    @srv.route("GET", "/api/fs/folder")
    def check_folder(req: Request):
        raw = req.arg("path") or ""
        if not raw.strip():
            raise HttpError(400, "informe uma pasta")
        return folder_info(expand(raw, app.env), app.env)

    @srv.route("GET", "/api/fs/recent")
    def recent_folders(_req: Request):
        seen = set()
        items: List[Dict[str, Any]] = []
        sites = {s.path: s.name for s in app.sites() if s.path}
        # sessões mais recentes primeiro, depois os sites que ainda não apareceram
        candidates = [(r.cwd, r.site) for r in app.hub.sessions.list() if r.cwd]
        candidates += [(path, name) for path, name in sites.items()]
        for raw, site in candidates:
            path = Path(os.path.abspath(raw))
            key = str(path)
            if key in seen or not path.is_dir():
                continue
            seen.add(key)
            items.append(folder_info(path, app.env, site or sites.get(key)))
            if len(items) >= RECENT_LIMIT:
                break
        home = Path(home_dir(app.env))
        return {"home": folder_info(home, app.env), "recent": items}
