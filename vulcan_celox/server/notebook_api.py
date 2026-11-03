"""Rotas JSON do caderno: tags, post-its, tarefas, progresso, busca e índice TAREFAS.md."""

from __future__ import annotations

import threading
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Optional

from vulcan_celox.core.markdown_index import (INDEX_FILENAME, ProjectIndexSettings, ProjectPathMissing,
                                                 global_index_path, render_global, render_project_block,
                                                 sync_project_indexes, write_if_changed, write_project_index)
from vulcan_celox.core.models import NOTE_COLORS, STATUSES, TAG_COLORS
from vulcan_celox.core.notebook import ALL, DuplicateTag, InvalidDue, chip_specs, task_summary
from vulcan_celox.core.progress import progress, progress_by_site, progress_by_tag
from vulcan_celox.core.search import search
from vulcan_celox.server.local_http import HttpError, Request

INDEX_DEBOUNCE_SECONDS = 0.5


def site_key(value: Any) -> Optional[str]:
    """'' ou ausente = Global (None)."""
    return str(value) if value not in (None, "") else None


def progress_dict(p) -> Dict[str, Any]:
    return {"total": p.total, "done": p.done, "doing": p.doing, "pct": p.pct, "label": p.label}


class NotebookApi:
    def __init__(self, app):
        self.app = app
        self.nb = app.notebook
        self.lock = threading.RLock()
        self.project_index = ProjectIndexSettings(app.store)
        self._timer: Optional[threading.Timer] = None
        self._timer_lock = threading.Lock()
        self.nb.subscribe(self._on_change)
        self.register(app.server)
        self.write_indexes()

    # ── índice ───────────────────────────────────────────────────────────
    def _on_change(self, kind: str) -> None:
        if kind not in ("tasks", "tags", "all"):
            return
        with self._timer_lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(INDEX_DEBOUNCE_SECONDS, self.write_indexes)
            self._timer.daemon = True
            self._timer.start()

    def flush_index(self) -> None:
        with self._timer_lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        self.write_indexes()

    def write_indexes(self) -> List[str]:
        with self.lock:
            tasks, tags = list(self.nb.tasks), dict(self.nb.tags)
        write_if_changed(global_index_path(self.app.data_dir), render_global(tasks, tags))
        site_paths = {s.name: s.path for s in self.app.sites()}
        return sync_project_indexes(self.project_index, site_paths, tasks, tags)

    # ── serialização ─────────────────────────────────────────────────────
    def chips(self, item) -> List[Dict[str, str]]:
        return [{"id": i, "name": n, "color": c} for i, n, c in chip_specs(item, self.nb.tags)]

    def terminal_title(self, terminal_id: Optional[str]) -> str:
        record = self.app.hub.sessions.get(terminal_id) if terminal_id else None
        return record.title if record else ""

    def note_dict(self, note) -> Dict[str, Any]:
        data = note.to_dict()
        data["site"] = note.site or ""
        data["title"] = note.title
        data["chips"] = self.chips(note)
        data["terminal"] = note.terminal or ""
        data["terminal_title"] = self.terminal_title(note.terminal)
        return data

    def task_dict(self, task) -> Dict[str, Any]:
        data = task.to_dict()
        data["site"] = task.site or ""
        data["chips"] = self.chips(task)
        data["terminal"] = task.terminal or ""
        data["terminal_title"] = self.terminal_title(task.terminal)
        return data

    def resolve_terminal(self, body: Dict[str, Any], site: Optional[str]):
        """(terminal, site): item criado numa sessão herda o site dela."""
        terminal = body.get("terminal") or None
        if not terminal:
            return None, site
        record = self.app.hub.sessions.get(str(terminal))
        if record is None:
            raise HttpError(404, "sessão de terminal não encontrada")
        return record.id, record.site

    def resolve_tags(self, values) -> List[str]:
        """Aceita ids existentes ou nomes (cria a tag quando o nome é novo)."""
        if values is None:
            return []
        if not isinstance(values, list):
            raise HttpError(400, "tags deve ser uma lista")
        ids = []
        for value in values:
            value = str(value).strip()
            if not value:
                continue
            tag_id = value if value in self.nb.tags else self.nb.ensure_tag(value).id
            if tag_id not in ids:
                ids.append(tag_id)
        return ids

    # ── rotas ────────────────────────────────────────────────────────────
    def register(self, srv) -> None:
        api = self

        def guarded(fn):
            @wraps(fn)
            def wrapper(req: Request):
                with api.lock:
                    try:
                        return fn(req)
                    except HttpError:
                        raise
                    except DuplicateTag:
                        raise HttpError(409, "já existe uma tag com esse nome") from None
                    except InvalidDue:
                        raise HttpError(400, "prazo inválido: use AAAA-MM-DD") from None
                    except KeyError:
                        raise HttpError(404, "item não encontrado") from None
                    except ValueError as exc:
                        raise HttpError(400, str(exc)) from None
            return wrapper

        def route(method, pattern):
            def decorator(fn):
                return srv.route(method, pattern)(guarded(fn))
            return decorator

        # tags
        @route("GET", "/api/tags")
        def list_tags(_req):
            usage: Dict[str, int] = {}
            for item in [*api.nb.notes, *api.nb.tasks]:
                for tag_id in item.tags:
                    usage[tag_id] = usage.get(tag_id, 0) + 1
            by_tag = progress_by_tag(api.nb.tasks)
            return {"palette": list(TAG_COLORS), "tags": [
                {**t.to_dict(), "usage": usage.get(t.id, 0),
                 "progress": progress_dict(by_tag[t.id]) if t.id in by_tag else None}
                for t in api.nb.sorted_tags()]}

        @route("POST", "/api/tags")
        def create_tag(req):
            body = req.json()
            return 201, api.nb.create_tag(str(body.get("name") or ""), body.get("color")).to_dict()

        @route("PATCH", r"/api/tags/(?P<tid>[0-9a-f]+)")
        def update_tag(req):
            body, tid = req.json(), req.params["tid"]
            if tid not in api.nb.tags:
                raise KeyError(tid)
            if "name" in body:
                api.nb.rename_tag(tid, str(body["name"]))
            if "color" in body:
                api.nb.set_tag_color(tid, str(body["color"]))
            return api.nb.tags[tid].to_dict()

        @route("DELETE", r"/api/tags/(?P<tid>[0-9a-f]+)")
        def delete_tag(req):
            if req.params["tid"] not in api.nb.tags:
                raise KeyError(req.params["tid"])
            api.app.hub.sessions.remove_tag_everywhere(req.params["tid"])
            return {"affected": api.nb.delete_tag(req.params["tid"])}

        # notas
        @route("GET", "/api/notes")
        def list_notes(req):
            tag = req.arg("tag") or None
            site = ALL if req.arg("site") == "*" else site_key(req.arg("site"))
            notes = api.nb.notes_for(site, req.arg("q", "") or "", tag, terminal=req.arg("terminal") or None)
            return {"colors": list(NOTE_COLORS), "notes": [api.note_dict(n) for n in notes]}

        @route("POST", "/api/notes")
        def create_note(req):
            body = req.json()
            terminal, site = api.resolve_terminal(body, site_key(body.get("site")))
            note = api.nb.add_note(site, str(body.get("text") or ""),
                                   str(body.get("color") or "amarelo"), api.resolve_tags(body.get("tags")),
                                   terminal=terminal)
            return 201, api.note_dict(note)

        @route("PATCH", r"/api/notes/(?P<nid>[0-9a-f]+)")
        def update_note(req):
            body, nid = req.json(), req.params["nid"]
            fields = {k: body[k] for k in ("text", "color", "pinned") if k in body}
            if "terminal" in body:
                fields["terminal"] = api.resolve_terminal(body, None)[0]
            note = api.nb.update_note(nid, **fields)
            if "tags" in body:
                api.nb.set_item_tags(note, api.resolve_tags(body["tags"]))
            return api.note_dict(note)

        @route("POST", r"/api/notes/(?P<nid>[0-9a-f]+)/move")
        def move_note(req):
            body = req.json()
            if body.get("target"):
                api.nb.reorder_note(req.params["nid"], target_id=str(body["target"]))
            else:
                api.nb.reorder_note(req.params["nid"], int(body.get("index", 0)))
            return {"ok": True}

        @route("DELETE", r"/api/notes/(?P<nid>[0-9a-f]+)")
        def delete_note(req):
            if api.nb.note(req.params["nid"]) is None:
                raise KeyError(req.params["nid"])
            api.nb.delete_note(req.params["nid"])
            return {"ok": True}

        # tarefas
        @route("GET", "/api/tasks")
        def list_tasks(req):
            site = ALL if req.arg("site") == "*" else site_key(req.arg("site"))
            statuses = [s for s in (req.arg("status") or "").split(",") if s in STATUSES] or None
            terminal = req.arg("terminal") or None
            tasks = api.nb.filter_tasks(site, statuses, req.arg("tag") or None, req.arg("sort", "priority"),
                                        terminal=terminal, assignee=req.arg("assignee") or None,
                                        due=req.arg("due") or None)
            base = api.nb.filter_tasks(site, terminal=terminal)
            return {"tasks": [api.task_dict(t) for t in tasks], "progress": progress_dict(progress(base)),
                    "summary": task_summary(base), "can_undo": api.nb.can_undo_delete()}

        @route("GET", "/api/tasks/assignees")
        def list_assignees(_req):
            counts: Dict[str, Dict[str, Any]] = {}
            for task in api.nb.tasks:
                if not task.assignee:
                    continue
                entry = counts.setdefault(task.assignee.casefold(), {"name": task.assignee, "open": 0, "total": 0})
                entry["total"] += 1
                entry["open"] += task.status != "done"
            return {"assignees": sorted(counts.values(), key=lambda e: e["name"].casefold())}

        @route("POST", "/api/tasks")
        def create_task(req):
            body = req.json()
            terminal, site = api.resolve_terminal(body, site_key(body.get("site")))
            task = api.nb.add_task(site, str(body.get("title") or ""),
                                   priority=body.get("priority", 2), tags=api.resolve_tags(body.get("tags")),
                                   due=body.get("due") or None, terminal=terminal, assignee=body.get("assignee"))
            return 201, api.task_dict(task)

        @route("PATCH", r"/api/tasks/(?P<tid>[0-9a-f]+)")
        def update_task(req):
            body, tid = req.json(), req.params["tid"]
            fields = {k: body[k] for k in ("title", "priority", "due", "status", "assignee") if k in body}
            if "terminal" in body:
                fields["terminal"] = api.resolve_terminal(body, None)[0]
            task = api.nb.update_task(tid, **fields) if fields else api.nb._task_or_raise(tid)
            if "tags" in body:
                api.nb.set_item_tags(task, api.resolve_tags(body["tags"]))
            return api.task_dict(task)

        @route("POST", r"/api/tasks/(?P<tid>[0-9a-f]+)/cycle")
        def cycle_task(req):
            return api.task_dict(api.nb.cycle_status(req.params["tid"]))

        @route("POST", r"/api/tasks/(?P<tid>[0-9a-f]+)/move")
        def move_task(req):
            api.nb.move_task(req.params["tid"], int(req.json().get("delta", 0)))
            return {"ok": True}

        @route("DELETE", r"/api/tasks/(?P<tid>[0-9a-f]+)")
        def delete_task(req):
            return {"deleted": api.task_dict(api.nb.delete_task(req.params["tid"]))}

        @route("POST", "/api/tasks/undo")
        def undo_task(_req):
            task = api.nb.undo_delete()
            if task is None:
                raise HttpError(410, "nada para desfazer")
            return api.task_dict(task)

        # progresso, busca, índice
        @route("GET", "/api/progress")
        def get_progress(_req):
            return {"overall": progress_dict(progress(api.nb.tasks)),
                    "sites": {(k or ""): progress_dict(p) for k, p in progress_by_site(api.nb.tasks).items()},
                    "tags": {k: progress_dict(p) for k, p in progress_by_tag(api.nb.tasks).items()}}

        @route("GET", "/api/search")
        def do_search(req):
            hits = search(req.arg("q", "") or "", api.app.sites(), api.nb)
            return {"hits": [h.__dict__ for h in hits]}

        @route("GET", "/api/index")
        def get_index(_req):
            api.flush_index()
            path = global_index_path(api.app.data_dir)
            return {"path": str(path), "markdown": path.read_text(encoding="utf-8") if path.exists() else ""}

        @route("GET", "/api/index/project")
        def get_project_index(req):
            name = req.arg("site") or ""
            return {"site": name, "enabled": api.project_index.enabled(name), "filename": INDEX_FILENAME,
                    "markdown": render_project_block(site_key(name), api.nb.tasks, api.nb.tags)}

        @route("POST", "/api/index/project")
        def set_project_index(req):
            body = req.json()
            site = api.app.site(body.get("site"))
            if site is None:
                raise HttpError(404, "site não encontrado")
            enabled = bool(body.get("enabled"))
            if enabled:
                try:
                    write_project_index(site.path, site.name, api.nb.tasks, api.nb.tags)
                except ProjectPathMissing:
                    api.project_index.set(site.name, False)
                    raise HttpError(400, f"pasta de '{site.name}' não existe") from None
            api.project_index.set(site.name, enabled)
            return {"site": site.name, "enabled": enabled, "path": str(Path(site.path) / INDEX_FILENAME)}
