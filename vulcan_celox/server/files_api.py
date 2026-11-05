"""Routes of the Code screen. Read-only: there is no write route under /api/files. The analyzed repository is third-party:
`git status`, `git diff` on the worktree and `ls-files -m` run programs from it, so they do not appear here."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

from vulcan_celox.core import code_diff, code_files, file_tree, file_watch, git_marks
from vulcan_celox.server.code_roots import CodeRoots
from vulcan_celox.server.files_agents import EditAttribution
from vulcan_celox.server.local_http import HttpError, Request


MAX_OPEN = 200
GIT_TTL = 30.0


class GitMarksCache:
    """Git marks per root. git runs again only when the sweep of the Code screen saw a change, or after GIT_TTL seconds
    (a commit only touches .git, which the sweep does not look at)."""

    def __init__(self, source=git_marks.collect, ttl: float = GIT_TTL, clock=time.monotonic):
        self.source, self.ttl, self.clock = source, ttl, clock
        self.lock = threading.Lock()
        self.items: Dict[str, Any] = {}
        self.runs = 0

    def get(self, root: str, seq: int) -> Dict[str, Any]:
        with self.lock:
            hit = self.items.get(root)
        if hit and hit[1] == seq and self.clock() - hit[0] < self.ttl:
            return hit[2]
        data = self.source(root)
        with self.lock:
            self.runs += 1
            self.items[root] = (self.clock(), seq, data)
        return data


def _stamp(root: str, rel: str):
    try:
        info = os.stat(os.path.join(root, rel))
    except OSError:
        return None
    return info.st_size, info.st_mtime_ns


class FilesService:
    def __init__(self, app):
        self.app = app
        self.roots = CodeRoots(app)
        self.ignores = file_tree.IgnoreCache()
        self.watches = file_watch.FileWatches(self.ignores.get)
        self.attribution = EditAttribution(app)
        self.git = GitMarksCache()

    def stop(self) -> None:
        self.watches.stop()

    def changes(self, req: Request, root: str) -> Dict[str, Any]:
        since = req.arg("since")
        try:
            cursor = int(since) if since not in (None, "") else None
        except ValueError:
            raise HttpError(400, "since deve ser um número") from None
        opened: List[str] = []
        for raw in (req.query.get("open") or [])[:MAX_OPEN]:
            try:
                opened.append(file_tree.clean_rel(raw))
            except code_files.CodeReadError:
                continue
        rel = self.rel(req, "file")
        watch = self.watches.watch(root)
        data = watch.poll(cursor, opened, rel)  # first the sweep that was due, so a fresh event already leaves with its author
        return {**data, "attributed": self.attribution.apply(root, watch.recent())}

    def root(self, req: Request) -> str:
        return self.roots.allowed(req.arg("root"))

    @staticmethod
    def rel(req: Request, name: str = "path") -> str:
        try:
            return file_tree.clean_rel(req.arg(name))
        except code_files.CodeReadError as err:
            raise HttpError(err.status, err.message, {"reason": err.reason}) from None

    def tree(self, root: str, rel: str) -> Dict[str, Any]:
        try:
            return file_tree.list_folder(root, rel, self.ignores.get(root))
        except code_files.CodeReadError as err:
            raise HttpError(err.status, err.message, {"reason": err.reason}) from None

    @staticmethod
    def read(root: str, rel: str) -> Dict[str, Any]:
        if not rel:
            raise HttpError(400, "caminho inválido", {"reason": "invalid"})
        try:
            before = _stamp(root, rel)
            data = code_files.read_for_viewer(rel, [root])
        except code_files.CodeReadError as err:
            raise HttpError(err.status, err.message, {"reason": err.reason}) from None
        if before != _stamp(root, rel):
            raise HttpError(409, "o arquivo mudou durante a leitura", {"reason": "changing"})
        return {**data, "rel": rel}

    def editor_path(self, root: Any, target: Any) -> Path:
        """The real file to hand to the editor. The page's word is not enough: the root, the path and the name are checked again."""
        real_root = self.roots.allowed(root if isinstance(root, str) else None)
        try:
            rel = file_tree.clean_rel(target if isinstance(target, str) else "")
            real = code_files.resolve_inside(rel, [real_root]) if rel else None
        except code_files.CodeReadError as err:
            raise HttpError(err.status, err.message, {"reason": err.reason}) from None
        if real is None or code_files.is_sensitive(rel) or code_files.is_sensitive(str(real)):
            raise HttpError(403, "este arquivo não pode ser aberto", {"reason": "sensitive"})
        if not real.is_file():
            raise HttpError(404, "arquivo não encontrado", {"reason": "missing"})
        return real

    @staticmethod
    def diff(root: str, rel: str) -> Dict[str, Any]:
        if not rel:
            raise HttpError(400, "caminho inválido", {"reason": "invalid"})
        try:
            real = code_files.resolve_inside(rel, [root])
        except code_files.CodeReadError as err:
            raise HttpError(err.status, err.message, {"reason": err.reason}) from None
        if code_files.is_sensitive(rel) or code_files.is_sensitive(str(real)):
            raise HttpError(403, "arquivo com nome sensível não é exibido", {"reason": "sensitive"})
        return {"rel": rel, "language": code_files.language_of(str(real)), "scope": "git", **code_diff.git_sides(real)}


def register_files_api(app) -> FilesService:
    service = FilesService(app)
    srv = app.server

    @srv.route("GET", "/api/files/roots")
    def _roots(_req: Request):
        return service.roots.listing()

    @srv.route("POST", "/api/files/roots")
    def _add_root(req: Request):
        return service.roots.add(req.json().get("path"))

    @srv.route("DELETE", "/api/files/roots")
    def _remove_root(req: Request):
        return service.roots.remove(req.arg("path"))

    @srv.route("GET", "/api/files/tree")
    def _tree(req: Request):
        return service.tree(service.root(req), service.rel(req))

    @srv.route("GET", "/api/files/read")
    def _read(req: Request):
        return service.read(service.root(req), service.rel(req))

    @srv.route("GET", "/api/files/diff")
    def _diff(req: Request):
        return service.diff(service.root(req), service.rel(req))

    @srv.route("GET", "/api/files/search")
    def _search(req: Request):
        root = service.root(req)
        text = req.arg("q") or ""
        if not text or "\x00" in text:
            raise HttpError(400, "falta o texto da busca", {"reason": "invalid"})
        return file_tree.git_search(root, text)

    @srv.route("GET", "/api/files/photo")
    def _photo(req: Request):
        watch = service.watches.watch(service.root(req))
        return {"files": watch.photo_files(), "partial": watch.partial}

    @srv.route("GET", "/api/files/git")
    def _git(req: Request):
        root = service.root(req)
        watch = service.watches.watch(root)
        watch.poll(None, watch.opened, watch.open_file)  # the sweep that was due runs first, as for the changes
        with watch.lock:
            seq = watch.seq
        data = service.git.get(root, seq)
        return {"marks": data["marks"], "truncated": data["truncated"], "branch": data["branch"], "repo": data["repo"]}

    @srv.route("GET", "/api/files/changes")
    def _changes(req: Request):
        return service.changes(req, service.root(req))

    return service
