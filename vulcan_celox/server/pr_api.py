"""Real PR state, optional: with the preference off no command runs and nothing leaves the machine."""

from __future__ import annotations

from vulcan_celox.core.pr_status import PrStatus
from vulcan_celox.server.known_roots import known_root
from vulcan_celox.server.local_http import HttpError, Request


def register_pr_api(app) -> PrStatus:
    status = PrStatus(app.runner, app.env)

    @app.server.route("GET", "/api/agents/pr")
    def _pr(req: Request):
        if not app.store.load("preferences", {}).get("pr_status", False):
            return {"source": "heuristic", "reason": "off"}
        sid = req.arg("session")
        if sid:
            session = app.agents.index.session(sid)
            if session is None:
                raise HttpError(404, "sessão de agente não encontrada")
            folder = session.cwd or session.project_root
        else:
            folder = req.arg("path") or ""
        # known folder only: gh runs in it, and the answer depends on what is in its .git
        if not folder or not known_root(app, folder):
            return {"source": "heuristic", "reason": "unknown_folder"}
        return status.status(folder)

    return status
