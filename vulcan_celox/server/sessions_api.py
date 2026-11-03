"""Rotas das sessões de terminal: listagem por site, detalhe, título e tags."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from vulcan_celox.core.progress import progress
from vulcan_celox.core.session_memory import doc_path
from vulcan_celox.core.trash import move_to_trash
from vulcan_celox.server.local_http import HttpError, Request
from vulcan_celox.server.notebook_api import site_key


def session_summary(app, record, agent_tags: Optional[Dict[str, list]] = None) -> Dict[str, Any]:
    """`agent_tags` ({aba: [{id, agent}]}) vem calculado uma vez por lista; sem ele, calcula aqui."""
    if agent_tags is None:
        agent_tags = app.hub.agent_tags()
    tasks = [t for t in app.notebook.tasks if t.terminal == record.id]
    notes = [n for n in app.notebook.notes if n.terminal == record.id]
    tags = app.notebook.tags
    p = progress(tasks)
    live = app.terminals.get(record.id)
    return {
        "id": record.id, "title": record.title, "site": record.site or "", "cwd": record.cwd,
        "created_at": record.created_at, "closed_at": record.closed_at, "exit_code": record.exit_code,
        "open": record.is_open, "live": bool(live and live.alive),
        "commands": len(record.commands), "last_command": record.commands[-1]["cmd"] if record.commands else "",
        "tasks": {"total": p.total, "done": p.done, "label": p.label}, "notes": len(notes),
        "tags": [{"id": t, "name": tags[t].name, "color": tags[t].color} for t in record.tags if t in tags],
        "memory_file": record.memory_file,
        "theme": record.theme, "agents": agent_tags.get(record.id, []),
        "has_doc": has_doc(record),
    }


def has_doc(record) -> bool:
    path = doc_path(record.memory_file)
    return bool(path and path.is_file())


def session_tree(app, closed_limit: int = 30) -> Dict[str, Any]:
    """Sessões abertas e as encerradas mais recentes, cada uma com seus itens, para a barra lateral."""
    split = app.hub.sessions.split("*")
    tasks_by: Dict[str, list] = {}
    notes_by: Dict[str, list] = {}
    for task in app.notebook.tasks:
        if task.terminal:
            tasks_by.setdefault(task.terminal, []).append(task)
    for note in app.notebook.notes:
        if note.terminal:
            notes_by.setdefault(note.terminal, []).append(note)
    order = {"doing": 0, "todo": 1, "done": 2}

    agent_tags = app.hub.agent_tags()

    def node(record) -> Dict[str, Any]:
        data = session_summary(app, record, agent_tags)
        tasks = sorted(tasks_by.get(record.id, []), key=lambda t: (order.get(t.status, 3), t.priority, t.order))
        data["task_list"] = [{"id": t.id, "title": t.title, "status": t.status} for t in tasks]
        data["note_list"] = [{"id": n.id, "title": n.title, "color": n.color} for n in notes_by.get(record.id, [])]
        return data

    closed = split["closed"]
    return {"open": [node(r) for r in split["open"]], "closed": [node(r) for r in closed[:closed_limit]],
            "closed_total": len(closed)}


def register_sessions_api(app) -> None:
    srv = app.server
    hub = app.hub
    lock = app.notebook_api.lock

    @srv.route("GET", "/api/sessions")
    def list_sessions(req: Request):
        site = "*" if req.arg("site") == "*" else site_key(req.arg("site"))
        with lock:
            split = hub.sessions.split(site)
            tags = hub.agent_tags()
            return {"open": [session_summary(app, r, tags) for r in split["open"]],
                    "closed": [session_summary(app, r, tags) for r in split["closed"]]}

    @srv.route("GET", "/api/sessions/tree")
    def tree(req: Request):
        try:
            limit = max(0, min(200, int(req.arg("closed") or 30)))
        except ValueError:
            raise HttpError(400, "closed deve ser um número") from None
        with lock:
            return session_tree(app, limit)

    @srv.route("GET", "/api/index/general")
    def general_index(_req: Request):
        path = hub.write_index()
        return {"path": str(path), "markdown": path.read_text(encoding="utf-8")}

    @srv.route("GET", r"/api/sessions/(?P<sid>[0-9a-f]+)")
    def get_session(req: Request):
        record = hub.sessions.get(req.params["sid"])
        if record is None:
            raise HttpError(404, "sessão não encontrada")
        with lock:
            data = session_summary(app, record)
            data["command_list"] = record.commands[-200:]
            data["memory"] = hub.memory_text(record)
            return data

    @srv.route("DELETE", r"/api/sessions/(?P<sid>[0-9a-f]+)")
    def delete_session(req: Request):
        record = hub.sessions.get(req.params["sid"])
        if record is None:
            raise HttpError(404, "sessão não encontrada")
        if record.is_open or app.terminals.get(record.id) is not None:
            raise HttpError(409, "feche o terminal antes de apagar a sessão")
        mode = req.arg("items", "keep")
        if mode not in ("keep", "delete"):
            raise HttpError(400, "items deve ser keep ou delete")
        nb = app.notebook
        with lock:
            tasks = [t for t in nb.tasks if t.terminal == record.id]
            notes = [n for n in nb.notes if n.terminal == record.id]
            for task in tasks:
                if mode == "delete":
                    nb.tasks.remove(task)
                else:
                    task.terminal = None  # continua no site, sem sessão
            for note in notes:
                if mode == "delete":
                    nb.notes.remove(note)
                else:
                    note.terminal = None
            if tasks:
                nb.changed("tasks")
            if notes:
                nb.changed("notes")
            hub.sessions.delete(record.id)
        moved = []
        for path in (record.memory_file, doc_path(record.memory_file)):
            if path and Path(path).exists():
                moved.append(str(move_to_trash(path, app.data_dir, app.runner)))
        hub.write_index()
        return {"ok": True, "items": mode, "tasks": len(tasks), "notes": len(notes), "moved": moved}

    @srv.route("PATCH", r"/api/sessions/(?P<sid>[0-9a-f]+)")
    def update_session(req: Request):
        record = hub.sessions.get(req.params["sid"])
        if record is None:
            raise HttpError(404, "sessão não encontrada")
        body = req.json()
        with lock:
            if "title" in body and str(body["title"]).strip():
                title = str(body["title"]).strip()[:60]
                hub.sessions.rename(record.id, title)
                live = app.terminals.get(record.id)
                if live:
                    live.title = title
            if "tags" in body:
                hub.sessions.set_tags(record.id, app.notebook_api.resolve_tags(body["tags"]))
            hub.on_session_changed(record.id)
            return session_summary(app, hub.sessions.get(record.id))
