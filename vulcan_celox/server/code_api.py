"""Routes of the session code viewer. Read-only: there is no write route under /api/code."""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from vulcan_celox.core import code_diff, code_files
from vulcan_celox.core.agents import edits as edit_log, turns as turn_log
from vulcan_celox.core.agents.model import AgentSession
from vulcan_celox.server.agents_api import SESSION_ID
from vulcan_celox.server.known_roots import known_folders, touches_agent_data
from vulcan_celox.server.local_http import HttpError, Request

SESSION_RE = re.compile("^" + SESSION_ID + "$")
SCOPES = ("edit", "turn", "git")
EDITS_PAGE = 200
EDITS_MAX = 500
ALL_EDITS = 5000  # a session with more than this shows the first ones in the tree and in the per-turn diff
MAX_DIFF = code_diff.MAX_OUTPUT
MAX_CANDIDATES = 50
RESOLVE_TTL = 5.0


def _int_arg(req: Request, name: str, default: Optional[int] = None, low: int = 0) -> Optional[int]:
    raw = req.arg(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise HttpError(400, f"{name} deve ser um número") from None
    if value < low:
        raise HttpError(400, f"{name} fora do intervalo")
    return value


class CodeService:
    def __init__(self, app):
        self.app = app
        self.resolved: Dict[Any, Any] = {}
        self.resolved_lock = threading.Lock()

    def session(self, sid: str) -> AgentSession:
        session = self.app.agents.index.session(sid) if sid and SESSION_RE.match(sid) else None
        if session is None:
            raise HttpError(404, "sessão de agente não encontrada")
        return session

    def roots(self, session: AgentSession) -> List[str]:
        """Session folders; one that is empty or touches the agents' data (the home folder, for example) does not count."""
        roots = [r for r in dict.fromkeys([session.project_root, session.cwd]) if r and not touches_agent_data(r, self.app.env)]
        if not roots:
            raise HttpError(403, "a pasta desta sessão não pode ser aberta no visor", {"reason": "root_refused"})
        return roots

    def read(self, session: AgentSession, path: str):
        try:
            return code_files.read_for_viewer(path, self.roots(session))
        except code_files.CodeReadError as err:
            raise HttpError(err.status, err.message, {"reason": err.reason}) from None

    @staticmethod
    def absolute(session: AgentSession, path: str) -> str:
        """The path as the agent recorded it may be relative to the session folder (Codex)."""
        return os.path.normpath(os.path.join(session.cwd or session.project_root or "/", path))

    def checked(self, session: AgentSession, path: str):
        """Real path inside the root and without a sensitive name: applies to all three scopes, because the diff carries the content."""
        try:
            real = code_files.resolve_inside(self.absolute(session, path), self.roots(session))
        except code_files.CodeReadError as err:
            raise HttpError(err.status, err.message, {"reason": err.reason}) from None
        if code_files.is_sensitive(path) or code_files.is_sensitive(str(real)):
            raise HttpError(403, "arquivo com nome sensível não é exibido", {"reason": "sensitive"})
        return real

    def rows(self, session: AgentSession, path: Optional[str] = None) -> List[Dict]:
        rows = edit_log.rows_of(self.app.agents.index, session.id, 0, ALL_EDITS)
        if path is None:
            return rows
        wanted = self.absolute(session, path)
        return [r for r in rows if self.absolute(session, r["path"]) == wanted]

    def tree(self, session: AgentSession) -> Dict[str, Any]:
        try:
            roots = self.roots(session)
        except HttpError:
            roots = []
        counts: Dict[str, Dict] = {}
        rows = self.rows(session)
        for row in rows:
            entry = counts.setdefault(self.absolute(session, row["path"]), {"edits": 0, "last_seq": 0, "failed": 0})
            entry["edits"] += 1
            entry["last_seq"] = row["seq"]
            entry["failed"] += row["state"] == "failed"
        files = []
        for touch in session.files:
            full = self.absolute(session, touch.path)
            inside = bool(roots) and self._inside(full, roots)
            files.append({"path": full, "rel": self._relative(full, roots), "kind": touch.kind, "last_at": touch.last_at,
                          "inside": inside, "sensitive": code_files.is_sensitive(full),
                          "exists": inside and os.path.lexists(full), "language": code_files.language_of(full),
                          **counts.get(full, {"edits": 0, "last_seq": 0, "failed": 0})})
        return {"root": roots[0] if roots else "", "root_refused": not roots, "files": files, "total_edits": len(rows),
                "last_seq": rows[-1]["seq"] if rows else 0, "is_active": session.is_active}

    @staticmethod
    def _inside(path: str, roots: List[str]) -> bool:
        try:
            code_files.resolve_inside(path, roots)
        except code_files.CodeReadError:
            return False
        return True

    @staticmethod
    def _relative(path: str, roots: List[str]) -> str:
        for root in roots:
            if path == root or path.startswith(root.rstrip("/\\") + os.sep):
                return os.path.relpath(path, root).replace(os.sep, "/")
        return path

    def diff(self, session: AgentSession, path: str, scope: str, seq: Optional[int]) -> Dict[str, Any]:
        if scope not in SCOPES:
            raise HttpError(400, "scope deve ser edit, turn ou git")
        real = self.checked(session, path)
        base = {"path": str(real), "scope": scope, "language": code_files.language_of(str(real))}
        if scope == "git":
            return {**base, **code_diff.git_sides(real)}
        rows = self.rows(session, path)
        chosen = next((r for r in rows if r["seq"] == seq), None) if seq is not None else (rows[-1] if rows else None)
        if chosen is None:
            raise HttpError(404, "edição não encontrada neste arquivo", {"reason": "no_edit"})
        picked = [chosen] if scope == "edit" else [r for r in rows if r["turn"] == chosen["turn"] and r["state"] != "failed"]
        return {**base, **self._compose(session, picked or [chosen]), "seq": chosen["seq"], "turn": chosen["turn"],
                "state": chosen["state"], "tool": chosen["tool"], "at": chosen["at"], "edits": [r["seq"] for r in picked]}

    @staticmethod
    def _compose(session: AgentSession, rows: List[Dict]) -> Dict[str, Any]:
        """One edit, or the snippets of several in order: joining snippets does not pretend to be the whole file."""
        details = [edit_log.edit_detail(session.agent, session.file_path, r) for r in rows]
        usable = [d for d in details if d["available"]]
        if not usable:
            return {"available": False, "reason": details[-1]["reason"], "truncated": False}
        old = "\n…\n".join(d["old"] for d in usable)
        new = "\n…\n".join(d["new"] for d in usable)
        truncated = len(old.encode()) > MAX_DIFF or len(new.encode()) > MAX_DIFF
        if truncated:
            old = old.encode()[:MAX_DIFF].decode("utf-8", "ignore")
            new = new.encode()[:MAX_DIFF].decode("utf-8", "ignore")
        return {"available": True, "old": old, "new": new, "truncated": truncated, "skipped": len(details) - len(usable),
                "complete": len(usable) == 1 and usable[0].get("complete", False) and not truncated,
                "replace_all": any(d.get("replace_all") for d in usable)}


    # ── caminhos clicados no terminal ───────────────────────────────────────
    def terminal_base(self, terminal: str):
        tab = self.app.terminals.get(terminal) if terminal else None
        if tab is None:
            raise HttpError(404, "aba não encontrada")
        paired = self.app.agents.paired_with(terminal)
        return tab.cwd, paired

    def resolve_one(self, cwd: str, paired: Optional[AgentSession], candidate: str) -> Optional[Dict[str, Any]]:
        """Answers only if it exists and is inside a known root. Sensitive files come back flagged, so the click can warn."""
        base = (paired.cwd if paired and paired.cwd else "") or cwd
        try:
            real = Path(base, candidate).resolve()
            if not real.exists():
                return None
            roots = [Path(r).resolve() for r in known_folders(self.app) + ([cwd] if self._known_cwd(cwd) else [])]
        except (OSError, ValueError, RuntimeError):
            return None
        if not any(real == r or real.is_relative_to(r) for r in roots):
            return None
        out = {"path": str(real), "kind": "dir" if real.is_dir() else "file",
               "sensitive": code_files.is_sensitive(candidate) or code_files.is_sensitive(str(real))}
        if out["kind"] == "file":
            # without a session the click goes to the Code screen, in the deepest known folder that holds the file
            holder = max((r for r in roots if real.is_relative_to(r)), key=lambda r: len(r.parts))
            out["root"], out["rel"] = str(holder), real.relative_to(holder).as_posix()
        if paired is not None and out["kind"] == "file":
            try:
                if self._inside(str(real), self.roots(paired)):
                    out["session"] = paired.id
            except HttpError:
                pass
        return out

    def _known_cwd(self, cwd: str) -> bool:
        """The tab's own folder counts, unless it contains the agents' data (the home folder, for example)."""
        return bool(cwd) and not touches_agent_data(cwd, self.app.env)

    def resolve(self, terminal: str, candidates: List[str]) -> Dict[str, Any]:
        cwd, paired = self.terminal_base(terminal)
        now = time.monotonic()
        results: Dict[str, Any] = {}
        for candidate in candidates:
            key = (terminal, paired.id if paired else "", candidate)
            with self.resolved_lock:
                cached = self.resolved.get(key)
            if cached and now - cached[0] < RESOLVE_TTL:
                result = cached[1]
            else:
                result = self.resolve_one(cwd, paired, candidate)
                with self.resolved_lock:
                    if len(self.resolved) > 2000:
                        self.resolved.clear()
                    self.resolved[key] = (now, result)
            if result:
                results[candidate] = result
        return results


def register_code_api(app) -> CodeService:
    service = CodeService(app)
    srv = app.server

    @srv.route("GET", "/api/code/file")
    def _file(req: Request):
        return service.read(service.session(req.arg("session") or ""), req.arg("path") or "")

    @srv.route("GET", f"/api/agents/sessions/{SESSION_ID}/turns")
    def _turns(req: Request):
        session = service.session(req.params["sid"])
        limit = min(_int_arg(req, "limit", 50, low=1), 200)
        data = turn_log.turns_of(app.agents.index, session.id, _int_arg(req, "start", 0), limit)
        for turn in data["turns"]:
            for file in turn["files"]:
                file["path"] = service.absolute(session, file["path"])  # o Codex grava relativo; a interface liga ao visor
        return data

    @srv.route("POST", "/api/code/resolve")
    def _resolve(req: Request):
        body = req.json()
        candidates = body.get("candidates")
        if not isinstance(candidates, list) or not all(isinstance(c, str) for c in candidates):
            raise HttpError(400, "candidates deve ser uma lista de caminhos")
        if len(candidates) > MAX_CANDIDATES:
            raise HttpError(400, f"no máximo {MAX_CANDIDATES} candidatos")
        return {"results": service.resolve(str(body.get("terminal") or ""), candidates)}

    @srv.route("GET", f"/api/code/session/{SESSION_ID}/tree")
    def _tree(req: Request):
        return service.tree(service.session(req.params["sid"]))

    @srv.route("GET", f"/api/code/session/{SESSION_ID}/edits")
    def _edits(req: Request):
        session = service.session(req.params["sid"])
        start = _int_arg(req, "start", 0)
        limit = min(_int_arg(req, "limit", EDITS_PAGE, low=1), EDITS_MAX)
        path = req.arg("path")
        if path:
            rows = [r for r in service.rows(session, path) if r["seq"] > start][:limit + 1]
        else:
            rows = edit_log.rows_of(app.agents.index, session.id, start, limit + 1)
        return {"edits": rows[:limit], "next": rows[limit - 1]["seq"] if len(rows) > limit else None}

    @srv.route("GET", f"/api/code/session/{SESSION_ID}/diff")
    def _diff(req: Request):
        path = req.arg("path") or ""
        if not path:
            raise HttpError(400, "falta o caminho", {"reason": "invalid"})
        return service.diff(service.session(req.params["sid"]), path, req.arg("scope") or "edit", _int_arg(req, "seq"))

    return service
