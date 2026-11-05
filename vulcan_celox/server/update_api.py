"""New version notice: at most one query a day, and none at all with the option off."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict

from vulcan_celox import __version__
from vulcan_celox.core.update_check import fetch_latest, is_newer
from vulcan_celox.server.local_http import HttpError, Request

STORE_KEY = "update_check"
INTERVAL = 24 * 3600


def register_update_api(app) -> None:
    srv = app.server
    lock = threading.Lock()
    app.update_transport = None  # tests replace it; None: the real network

    def saved() -> Dict[str, Any]:
        data = app.store.load(STORE_KEY, {})
        return data if isinstance(data, dict) else {}

    def allowed() -> bool:
        return app.env.get("VULCAN_UPDATE_CHECK") != "0"

    def enabled(data: Dict[str, Any]) -> bool:
        return allowed() and data.get("enabled", True) is True

    def payload(data: Dict[str, Any]) -> Dict[str, Any]:
        latest = data.get("latest")
        return {"enabled": enabled(data), "current": __version__, "latest": latest, "url": data.get("url"),
                "newer": is_newer(latest, __version__), "reason": data.get("reason"),
                "checked_at": data.get("checked_at"), "dismissed": data.get("dismissed")}

    def query(data: Dict[str, Any]) -> Dict[str, Any]:
        found = fetch_latest(app.env, app.runner, __version__, app.update_transport)
        data = {**data, "checked_at": time.time()}
        if "reason" in found:  # keeps what was already known
            data["reason"] = found["reason"]
        else:
            data = {**data, **found, "reason": None}
        app.store.save(STORE_KEY, data)
        return data

    @srv.route("GET", "/api/update")
    def _status(_req: Request):
        with lock:
            data = saved()
            stale = time.time() - float(data.get("checked_at") or 0) >= INTERVAL
            if enabled(data) and stale:
                data = query(data)
            return payload(data)

    @srv.route("POST", "/api/update/check")
    def _check(_req: Request):
        with lock:
            data = saved()
            if not allowed():
                raise HttpError(409, "a consulta de versão está desligada neste ambiente")
            return payload(query(data))

    @srv.route("PUT", "/api/update")
    def _set(req: Request):
        body = req.json()
        with lock:
            data = saved()
            if "enabled" in body:
                if not isinstance(body["enabled"], bool):
                    raise HttpError(400, "enabled deve ser verdadeiro ou falso")
                data["enabled"] = body["enabled"]
            if "dismissed" in body:
                if not isinstance(body["dismissed"], str):
                    raise HttpError(400, "dismissed deve ser uma versão")
                data["dismissed"] = body["dismissed"][:32]
            app.store.save(STORE_KEY, data)
            return payload(data)
