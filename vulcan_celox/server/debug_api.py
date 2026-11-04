"""Debugging: events from the Lerd dump bridge and its switch."""

from __future__ import annotations

from urllib.parse import urlencode

from vulcan_celox.core.lerd_dumps import (API_FILTERS, event_text, events_for_session, filter_min_ms, group_by_request,
                                             group_queries, log_tone, parse_events, session_summary, site_for_path)
from vulcan_celox.server.local_http import HttpError, Request

MAX_LIMIT = 2000


def register_debug_api(app) -> None:
    srv = app.server

    def lerd():
        b = app.backend
        if not (b.available and b.name == "lerd"):
            raise HttpError(409, "a depuração usa a ponte de dumps do Lerd; ela não existe no Valet nem sem backend")
        return b

    @srv.route("GET", "/api/debug/events")
    def events(req: Request):
        b = lerd()
        params = {k: req.arg(k) for k in API_FILTERS if req.arg(k)}
        limit = req.arg("limit") or "500"
        params["limit"] = str(min(MAX_LIMIT, int(limit))) if limit.isdigit() else "500"
        rows = b.api_get(f"/api/dumps?{urlencode(params)}", timeout=5.0)
        found = parse_events(rows)
        q = (req.arg("q") or "").strip().lower()
        if q:
            found = [e for e in found if q in event_text(e).lower()]
        raw_min = req.arg("min_ms") or ""
        found = filter_min_ms(found, float(raw_min) if raw_min.replace(".", "", 1).isdigit() else 0)
        for e in found:
            if e["kind"] == "log":
                e["tone"] = log_tone(e["data"].get("level"))
        if req.arg("group") == "1":
            groups = group_by_request(found)
            for g in groups:  # repeated queries in the same request
                g["queries"] = group_queries(g["events"])
            return {"groups": groups, "available": rows is not None}
        return {"events": found, "available": rows is not None}

    def bridge_state(b):
        status = b.api_get("/api/dumps/status")
        status = status if isinstance(status, dict) else {}
        return {"enabled": bool(status.get("enabled")), "count": int(status.get("count") or 0),
                "capacity": int(status.get("capacity") or 0), "listening": bool(status.get("listening")),
                "addr": str(status.get("addr") or "")}

    @srv.route("GET", "/api/debug/bridge")
    def bridge(_req: Request):
        return bridge_state(lerd())

    @srv.route("PUT", "/api/debug/bridge")
    def set_bridge(req: Request):
        b = lerd()
        enabled = req.json().get("enabled")
        if not isinstance(enabled, bool):
            raise HttpError(400, "enabled deve ser true ou false")
        code = b.api_post("/api/dumps/toggle", {"enable": enabled})
        if code >= 400 or code == 0:
            raise HttpError(502, f"o Lerd recusou ligar ou desligar a ponte (HTTP {code})")
        return bridge_state(b)

    @srv.route("POST", "/api/debug/clear")
    def clear(_req: Request):
        b = lerd()
        code = b.api_post("/api/dumps/clear")
        if code >= 400 or code == 0:
            raise HttpError(502, f"o Lerd recusou limpar (HTTP {code})")
        return bridge_state(b)

    @srv.route("GET", r"/api/debug/agent/(?P<sid>[A-Za-z0-9][A-Za-z0-9._-]{0,79})")
    def agent_session(req: Request):
        """Exceptions and error logs of the agent session's site between its start and last activity."""
        s = app.agents.index.session(req.params["sid"])
        if not s:
            raise HttpError(404, "sessão de agente não encontrada")
        b = app.backend
        site = site_for_path([(x.name, x.path) for x in app.sites()], s.cwd or s.project_root)
        if not (b.available and b.name == "lerd") or not site:
            return {"available": False, "site": site, "events": [], "summary": ""}
        rows = b.api_get(f"/api/dumps?{urlencode({'site': site, 'kind': 'log', 'limit': str(MAX_LIMIT)})}", timeout=5.0)
        found = events_for_session(parse_events(rows), site, s.started_at, s.last_activity_at)
        for e in found:
            e["tone"] = log_tone(e["data"].get("level"))
        return {"available": rows is not None, "site": site, "events": found,
                "summary": session_summary(found, site) if found else ""}

