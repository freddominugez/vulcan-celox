"""The user's data: backup, restore, and masking what was saved before the mask existed."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict

from vulcan_celox import __version__
from vulcan_celox.core.backup import BackupError, create_backup, prepare_restore, restore_pending
from vulcan_celox.core.backup_inspect import inspect_backup, list_restores, restore_folder
from vulcan_celox.core.memory_mask import mask_saved_memories
from vulcan_celox.core.trash import move_to_trash
from vulcan_celox.server.fs_api import expand, home_dir
from vulcan_celox.server.local_http import HttpError, Request

STORE_KEY = "backup"
DEFAULT_FOLDER = ("Documents", "Vulcan Celox Backups")


def register_data_api(app) -> None:
    srv = app.server
    from vulcan_celox.server.update_api import register_update_api
    register_update_api(app)

    def saved() -> Dict[str, Any]:
        data = app.store.load(STORE_KEY, {})
        return data if isinstance(data, dict) else {}

    def payload() -> Dict[str, Any]:
        data = saved()
        folder = data.get("folder") or str(Path(home_dir(app.env)).joinpath(*DEFAULT_FOLDER))
        return {"folder": folder, "last": data.get("last"), "restore_pending": restore_pending(app.data_dir),
                "restore_error": app.restore_error}

    def path_arg(req: Request, field: str) -> Path:
        raw = req.json().get(field)
        if not isinstance(raw, str) or not raw.strip():
            raise HttpError(400, "informe o caminho")
        return expand(raw, app.env)

    @srv.route("GET", "/api/data/backup")
    def _status(_req: Request):
        return payload()

    @srv.route("POST", "/api/data/backup")
    def _backup(req: Request):
        folder = path_arg(req, "folder")
        app.hub.flush_open()  # the zip has what is on screen, not what was on disk a few seconds ago
        try:
            result = create_backup(app.data_dir, folder, __version__)
        except BackupError as exc:
            raise HttpError(400, str(exc)) from None
        app.store.save(STORE_KEY, {"folder": str(folder), "last": {**result, "at": time.time()}})
        return {**payload(), "created": result}

    @srv.route("POST", "/api/data/restore")
    def _restore(req: Request):
        try:
            info = prepare_restore(path_arg(req, "path"), app.data_dir)
        except BackupError as exc:
            raise HttpError(400, str(exc)) from None
        return {**payload(), "restore": info}

    @srv.route("POST", "/api/data/backup/inspect")
    def _inspect(req: Request):
        try:
            return inspect_backup(path_arg(req, "path"), app.data_dir, __version__)
        except BackupError as exc:
            raise HttpError(400, str(exc)) from None

    @srv.route("GET", "/api/data/restores")
    def _restores(_req: Request):
        return {"restores": list_restores(app.data_dir)}

    @srv.route("POST", "/api/data/restores/trash")
    def _restore_trash(req: Request):
        try:
            folder = restore_folder(app.data_dir, req.json().get("name"))
        except BackupError as exc:
            raise HttpError(400, str(exc)) from None
        move_to_trash(folder, app.data_dir, app.runner)
        return {"restores": list_restores(app.data_dir)}

    @srv.route("POST", "/api/data/mask-saved")
    def _mask(_req: Request):
        app.hub.flush_open()
        files, secrets = mask_saved_memories(app.data_dir)
        return {"files": files, "secrets": secrets, "commands": app.hub.sessions.mask_commands()}
