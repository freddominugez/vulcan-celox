"""Button prompt routes: list rendered with the session, prompt creation and category creation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from vulcan_celox.core import procinfo, prompts
from vulcan_celox.core.agents.model import AgentSession
from vulcan_celox.server.agents_api import card
from vulcan_celox.server.known_roots import known_root
from vulcan_celox.server.local_http import HttpError, Request

SCOPES = ("global", "project")


def is_prompt_file(path: Path, global_dir: Path) -> bool:
    """Only .md files from the global prompts folder or from some <project>/.vulcan/prompts/ may be opened."""
    try:
        real = path.resolve()
    except OSError:
        return False
    if real.suffix != ".md" or not real.is_file():
        return False
    if real.is_relative_to(global_dir.resolve()):
        return True
    return any(p.name == "prompts" and p.parent.name == ".vulcan" for p in real.parents)


class PromptsService:
    def __init__(self, app):
        self.app = app
        self.global_dir = Path(app.data_dir) / "prompts"
        prompts.seed_global(self.global_dir)

    def session_for(self, req: Request) -> Optional[AgentSession]:
        """Requested session; otherwise the one paired with the tab (terminal); otherwise the most recent in the terminal's folder (cwd);
        otherwise the current session."""
        agents = self.app.agents
        sid = req.arg("session")
        if sid:
            session = agents.index.session(sid)
            if session is None:
                raise HttpError(404, "sessão de agente não encontrada")
            return agents.decorate([session])[0]
        terminal = req.arg("terminal")
        if terminal:
            paired = agents.paired_with(terminal)
            if paired is not None:
                return paired
        cwd = (req.arg("cwd") or "").rstrip("/")
        if cwd:
            for s in agents.decorate(agents.index.sessions()):  # from newest to oldest
                if cwd in (s.project_root.rstrip("/"), s.cwd.rstrip("/")) or s.cwd.startswith(cwd + "/"):
                    return s
        return agents.current_session()

    def listing(self, session: Optional[AgentSession], pinned: bool = False) -> Dict[str, Any]:
        context = self.app.agents.context(session)
        root = (session.project_root or session.cwd) if session else ""
        project = prompts.project_dir(root) if root else None
        loaded, warnings = prompts.load_all(self.global_dir, project)
        items = []
        for p in loaded:
            if pinned and not p.pin:
                continue
            rendered, missing = prompts.render(p.body, context)
            items.append({**p.to_dict(), "rendered": rendered, "missing": missing,
                          "summary": prompts.summary(p, context)})
        counts: Dict[str, int] = {}
        for p in loaded:
            counts[p.category] = counts.get(p.category, 0) + 1
        names: List[str] = prompts.default_categories()
        for name in [p.category for p in loaded] + prompts.categories(self.global_dir) + \
                (prompts.categories(project) if project else []):
            if name not in names:
                names.append(name)
        chosen = self.app.agents.chosen_id()
        return {
            "prompts": items, "warnings": warnings, "context": context, "variables": list(prompts.VARIABLES),
            "labels": prompts.label_names(),
            "categories": [{"name": n, "count": counts.get(n, 0), "user": n not in prompts.default_categories()} for n in names],
            "session": card(session) if session else None,
            "automatic": not (session and session.id == chosen),
            "global_dir": str(self.global_dir),
            "project": {"root": root, "dir": str(project) if project else "", "exists": bool(project and project.is_dir())},
        }

    def target_dir(self, body: Dict) -> Path:
        scope = body.get("scope", "global")
        if scope not in SCOPES:
            raise HttpError(400, "scope deve ser global ou project")
        if scope == "global":
            return self.global_dir
        root = body.get("project_root")
        if not isinstance(root, str) or not Path(root).is_dir():
            raise HttpError(400, "pasta do projeto não existe")
        if not known_root(self.app, root):
            raise HttpError(400, "a pasta não é de um site, projeto Node ou sessão de agente conhecida")
        folder = prompts.project_dir(root)
        if not folder.is_dir() and body.get("confirm_project_dir") is not True:
            # writing to a project folder only with opt-in: the interface asks before creating .vulcan/prompts
            raise HttpError(409, "confirme a criação da pasta de prompts do projeto",
                            {"needs_confirmation": True, "dir": str(folder)})
        return folder


def register_prompts_api(app) -> PromptsService:
    srv = app.server
    service = PromptsService(app)

    @srv.route("GET", "/api/prompts")
    def list_prompts(req: Request):
        return service.listing(service.session_for(req), pinned=req.arg("pinned") in ("1", "true"))

    @srv.route("POST", "/api/prompts")
    def create_prompt(req: Request):
        body = req.json()
        title, category = body.get("title"), body.get("category", "")
        if not isinstance(title, str) or not title.strip() or not isinstance(category, str):
            raise HttpError(400, "title e category devem ser texto")
        path = prompts.create_prompt(service.target_dir(body), title, category)
        return {"path": str(path)}

    @srv.route("POST", "/api/prompts/send")
    def send(req: Request):
        """Pastes the prompt text into the tab paired with the session, without Enter. With no live paired tab, 409
        with what the interface needs to offer resuming the session in a terminal."""
        body = req.json()
        pid, sid, values = body.get("prompt"), body.get("session"), body.get("values") or {}
        if not isinstance(pid, str) or not pid:
            raise HttpError(400, "informe o prompt")
        if sid is not None and not isinstance(sid, str):
            raise HttpError(400, "session deve ser texto")
        if not isinstance(values, dict) or not all(isinstance(k, str) and isinstance(v, str) and len(v) <= prompts.VALUE_MAX
                                                   for k, v in values.items()):
            raise HttpError(400, f"values deve mapear nome para texto de até {prompts.VALUE_MAX} caracteres")
        agents = app.agents
        if sid:
            found = agents.index.session(sid)
            if found is None:
                raise HttpError(404, "sessão de agente não encontrada")
            session = agents.decorate([found])[0]
        else:
            session = agents.current_session()
        if session is None:
            raise HttpError(409, "nenhuma sessão de agente para receber o prompt", {"needs_terminal": True, "session": None})
        root = session.project_root or session.cwd
        loaded, _ = prompts.load_all(service.global_dir, prompts.project_dir(root) if root else None)
        prompt = next((p for p in loaded if p.id == pid), None)
        if prompt is None:
            raise HttpError(404, "prompt não encontrado")
        data, missing = prompts.paste_bytes(prompt.body, agents.context(session), values)
        if missing:
            raise HttpError(400, f"preencha: {', '.join(prompts.label_names().get(m, m) for m in missing)}", {"missing": missing})
        terminal = app.terminals.get(session.pairing_id) if session.pairing_id else None
        if terminal is None or not terminal.alive:
            raise HttpError(409, "a sessão não tem terminal aberto e pareado",
                            {"needs_terminal": True, "session": session.id})
        # the pairing expires with the agent. Another, newer session in the tab, or the tab back at the shell,
        # e o prompt cairia no lugar errado.
        newest = agents.paired_with(terminal.id)
        foreground = terminal.foreground() if hasattr(terminal, "foreground") else None
        if (newest is not None and newest.id != session.id) or \
                (foreground is not None and not procinfo.agent_running(foreground, session.agent)):
            raise HttpError(409, "o agente desta sessão não está mais rodando na aba pareada",
                            {"needs_terminal": True, "session": session.id})
        if terminal.write(data) is False:  # paste without Enter: the user is the one who sends it, in the terminal
            raise HttpError(503, "a aba não leu a colagem a tempo; confira o terminal", {"terminal": terminal.id})
        return {"terminal": terminal.id, "title": getattr(terminal, "title", ""), "session": session.id}

    @srv.route("POST", "/api/prompts/categories")
    def create_category(req: Request):
        body = req.json()
        name = body.get("name")
        if not isinstance(name, str) or not name.strip():
            raise HttpError(400, "name deve ser texto")
        folder = prompts.create_category(service.target_dir(body), name)
        return {"path": str(folder)}

    return service
