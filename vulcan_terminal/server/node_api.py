"""Projetos Node (vt-25): lista guardada pelo app, detalhe lido do disco e sugestões vindas das sessões dos agentes.

A lista é só do app (`node_projects` no Store): tirar um projeto dela não toca na pasta.
"""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

from vulcan_terminal.core import node_project
from vulcan_terminal.server.local_http import HttpError, Request

NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
NAME_RE = r"(?P<name>[a-z0-9][a-z0-9._-]{0,63})"
SUGGEST_LIMIT = 12
STORE_KEY = "node_projects"
SUPABASE_ACTIONS = ("start", "stop", "status")
CTRL_C = b"\x03"


def slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9._-]+", "-", text.lower()).strip("-._")
    return (value or "projeto")[:64]


def register_node_api(app) -> "NodeProjects":
    projects = NodeProjects(app)
    srv = app.server

    @srv.route("GET", "/api/node-projects")
    def list_projects(req: Request):
        return {"projects": [projects.summary(n, p) for n, p in sorted(projects.saved().items())]}

    @srv.route("POST", "/api/node-projects")
    def add(req: Request):
        body = req.json()
        raw = str(body.get("path") or "")
        if not raw or not os.path.isabs(os.path.expanduser(raw)):
            raise HttpError(400, "informe o caminho completo da pasta")
        path = Path(os.path.abspath(os.path.expanduser(raw)))
        if not path.is_dir():
            raise HttpError(400, "pasta não existe")
        if not (path / "package.json").is_file():
            raise HttpError(400, "a pasta não tem package.json na raiz")
        name = str(body.get("name") or slug(path.name))
        if not NAME.match(name):
            raise HttpError(400, "nome só com letras minúsculas, números, ponto, hífen e sublinhado")
        with projects.list_lock:  # ler, mudar e salvar juntos: dois pedidos ao mesmo tempo não perdem projeto
            saved = projects.saved()
            if name in saved:
                raise HttpError(409, "já existe um projeto com esse nome")
            if str(path) in saved.values():
                raise HttpError(409, "essa pasta já está na lista")
            saved[name] = str(path)
            app.store.save(STORE_KEY, saved)
        return projects.summary(name, str(path))

    @srv.route("GET", "/api/node-projects/suggest")
    def suggest(req: Request):
        return {"suggestions": projects.suggestions()}

    @srv.route("GET", rf"/api/node-projects/{NAME_RE}")
    def detail(req: Request):
        name = req.params["name"]
        return projects.detail(name, projects.path_or_404(name))

    @srv.route("POST", rf"/api/node-projects/{NAME_RE}/run")
    def run(req: Request):
        name = req.params["name"]
        path = projects.path_or_404(name)
        script = str(req.json().get("script") or "")
        if not node_project.SCRIPT_NAME.match(script):
            raise HttpError(400, "nome de script inválido")
        info = node_project.read(Path(path))
        if info.get("estado") != "ok":
            raise HttpError(409, "package.json ilegível ou ausente")
        if script not in node_project.scripts_list(info):
            raise HttpError(400, f"o package.json não tem o script {script}")
        typed = node_project.run_command(info["gerenciador"], script)
        return 201, projects.start(name, path, script, typed)

    @srv.route("POST", rf"/api/node-projects/{NAME_RE}/supabase/(?P<action>[a-z]+)")
    def supabase(req: Request):
        name = req.params["name"]
        path = projects.path_or_404(name)
        action = req.params["action"]
        if action not in SUPABASE_ACTIONS:
            raise HttpError(400, "ação do Supabase deve ser start, stop ou status")
        if not (Path(path) / "supabase" / "config.toml").is_file():
            raise HttpError(409, "o projeto não tem supabase/config.toml")
        return 201, projects.start(name, path, f"supabase {action}", f"supabase {action}")

    @srv.route("POST", rf"/api/node-projects/{NAME_RE}/stop")
    def stop(req: Request):
        name = req.params["name"]
        projects.path_or_404(name)
        terminal = str(req.json().get("terminal") or "")
        if not projects.owns(name, terminal):
            raise HttpError(404, "esta aba não roda script deste projeto")
        session = app.terminals.get(terminal)
        if session is None or not session.alive:
            raise HttpError(409, "a aba já foi fechada")
        session.write(CTRL_C)  # Ctrl-C na aba do próprio projeto; a aba fica aberta com a saída
        return {"ok": True}

    @srv.route("POST", rf"/api/node-projects/{NAME_RE}/remove")
    def remove(req: Request):
        name = req.params["name"]
        projects.path_or_404(name)
        with projects.list_lock:
            saved = projects.saved()
            saved.pop(name, None)
            app.store.save(STORE_KEY, saved)
        return {"ok": True}

    return projects


class NodeProjects:
    def __init__(self, app):
        self.app = app
        self._lock = threading.Lock()
        self.list_lock = threading.Lock()  # vt-28 C3: a lista salva de projetos
        self._runs: Dict[str, List[Dict[str, Any]]] = {}  # projeto -> abas abertas por ele (memória desta execução)

    def start(self, name: str, path: str, label: str, typed: str) -> Dict[str, Any]:
        session = self.app.spawn_terminal(path, f"{name} · {label}", None, typed=typed)
        with self._lock:
            self._runs.setdefault(name, []).append({"terminal": session.id, "script": label, "comando": typed,
                                                    "inicio": time.time()})
        return {"terminal": session.id, "comando": typed, "title": getattr(session, "title", label)}

    def owns(self, name: str, terminal: str) -> bool:
        with self._lock:
            return any(r["terminal"] == terminal for r in self._runs.get(name, []))

    def running(self, name: str) -> List[Dict[str, Any]]:
        """Abas ainda abertas que rodam scripts do projeto, com a primeira URL local vista na saída."""
        out, alive = [], []
        with self._lock:
            runs = list(self._runs.get(name, []))
        for r in runs:
            session = self.app.terminals.get(r["terminal"])
            if session is None or not session.alive:
                continue
            alive.append(r)
            text = session.history()[-200000:].decode("utf-8", "replace")
            out.append({**r, "url": node_project.local_url(text)})
        with self._lock:
            self._runs[name] = [r for r in self._runs.get(name, []) if r in alive or r not in runs]
        return out

    def saved(self) -> Dict[str, str]:
        data = self.app.store.load(STORE_KEY, {})
        if not isinstance(data, dict):
            return {}
        return {str(k): str(v) for k, v in data.items() if NAME.match(str(k)) and isinstance(v, str)}

    def path_or_404(self, name: str) -> str:
        path = self.saved().get(name)
        if path is None:
            raise HttpError(404, "projeto não encontrado")
        return path

    def summary(self, name: str, path: str) -> Dict[str, Any]:
        info = node_project.read(Path(path)) if Path(path).is_dir() else {"estado": "sumiu"}
        fw = info.get("framework") or {}
        return {"name": name, "path": path, "estado": info.get("estado"), "nome": info.get("nome"),
                "framework": fw.get("nome"), "gerenciador": info.get("gerenciador"),
                "porta": info.get("porta_provavel"), "supabase": bool(info.get("supabase")),
                "vercel": bool(info.get("vercel"))}

    def detail(self, name: str, path: str) -> Dict[str, Any]:
        info = node_project.read(Path(path)) if Path(path).is_dir() else {"estado": "sumiu", "pasta": path}
        info["name"] = name
        info["rodando"] = self.running(name)
        return info

    def suggestions(self) -> List[Dict[str, str]]:
        """Pastas onde os agentes trabalharam que têm package.json e ainda não estão na lista (mais recentes antes)."""
        agents = getattr(self.app, "agents", None)
        if agents is None:
            return []
        taken = set(self.saved().values())
        seen, out = set(), []
        sessions = sorted(agents.index.sessions(), key=lambda s: s.last_activity_at or "", reverse=True)
        for s in sessions:
            folder = s.project_root or s.cwd
            if not folder or folder in seen or folder in taken:
                continue
            seen.add(folder)
            if os.path.isfile(os.path.join(folder, "package.json")):
                out.append({"path": folder, "name": slug(os.path.basename(folder.rstrip("/")))})
                if len(out) >= SUGGEST_LIMIT:
                    break
        return out
