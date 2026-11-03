"""Rotas das sessões de agente (Claude Code e Codex): lista com KPIs, detalhe com eventos e revisão do índice."""

from __future__ import annotations

import shutil
import sys
import threading
from collections import OrderedDict
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


from vulcan_celox.core import harness, procinfo, prompts, themes
from vulcan_celox.core.agents import attention, attention_hook, discovery, pairing, pricing, repos, usage
from vulcan_celox.core.agents.history import KINDS
from vulcan_celox.core.textutil import headline
from vulcan_celox.core.agents.index import AgentIndex, index_path
from vulcan_celox.core.agents.status import claude_cleanup_days
from vulcan_celox.core.agents.model import AgentSession, local_day
from vulcan_celox.core.agents.watcher import AgentWatcher
from vulcan_celox.server.local_http import HttpError, RawResponse, Request

SESSION_ID = r"(?P<sid>[A-Za-z0-9][A-Za-z0-9._-]{0,79})"  # começa por letra ou dígito: nada de opção
UNPUBLISHED = ("none", "committed")
RESUME_COMMANDS = {"claude": "claude --resume {id}", "codex": "codex resume {id}"}
CONTEXT_TTL = 30.0


def is_unpublished(s: AgentSession) -> bool:
    return s.edited_total() > 0 and s.published in UNPUBLISHED


def card(s: AgentSession) -> Dict[str, Any]:
    edited = s.edited_total()
    return {
        "id": s.id, "agent": s.agent, "project": s.project_name, "project_root": s.project_root, "cwd": s.cwd,
        "branch": s.git_branch, "worktree": s.worktree, "title": s.title, "ask": s.first_user_message,
        "headline": headline(s.title or s.first_user_message),
        "started_at": s.started_at, "last_activity_at": s.last_activity_at, "is_active": s.is_active,
        "model": s.model, "cli_version": s.cli_version, "turns": s.turns,
        "files_edited": edited, "files_read": s.files_total() - edited, "commands": s.commands_total,
        "published": s.published, "pr_opened": s.pr_opened, "unpublished": is_unpublished(s),
        "tokens": s.tokens, "loop": s.loop_alert, "subagents": s.subagents,
        "theme": s.theme, "pairing_id": s.pairing_id, "attention": attention.resolve(s.attention, hook=s.attention_hook),
    }


def detail(s: AgentSession) -> Dict[str, Any]:
    data = card(s)
    data["files"] = [{"path": f.path, "kind": f.kind, "first_at": f.first_at, "last_at": f.last_at} for f in s.files]
    data["command_list"] = [{"text": c.text, "at": c.at, "kind": c.kind, "exit_code": c.exit_code} for c in s.commands]
    data["file_path"] = s.file_path
    data["parse_errors"] = s.parse_errors
    return data


def kpis(sessions: Iterable[AgentSession], today: Optional[str] = None,
         edited_today: Optional[int] = None) -> Dict[str, int]:
    """`edited_today` vem do índice quando a lista é leve (sem arquivos); senão é contado aqui."""
    sessions = list(sessions)
    today = today or datetime.now().astimezone().date().isoformat()
    of_today = [s for s in sessions if local_day(s.last_activity_at) == today]
    return {
        "active": sum(1 for s in sessions if s.is_active),
        # pela data de cada arquivo: uma sessão longa que só teve uma atividade hoje não soma o que fez antes
        "files_edited_today": edited_today if edited_today is not None
        else sum(1 for s in sessions for f in s.edited_files() if local_day(f.last_at) == today),
        "unpublished": sum(1 for s in sessions if is_unpublished(s)),
        "tokens_today": sum((s.tokens or {}).get("input", 0) + (s.tokens or {}).get("output", 0) for s in of_today),
        "sessions_today": len(of_today),
    }


def matches(s: AgentSession, req: Request) -> bool:
    agent, project, cwd = req.arg("agent"), req.arg("project"), req.arg("cwd")
    if agent and s.agent != agent:
        return False
    if req.arg("active") in ("1", "true") and not s.is_active:
        return False
    if req.arg("unpublished") in ("1", "true") and not is_unpublished(s):
        return False
    if project and s.project_name != project:
        return False
    if cwd and not (s.cwd == cwd or s.project_root == cwd or s.cwd.startswith(cwd.rstrip("/") + "/")):
        return False
    return True


def _int(req: Request, name: str, default: int, low: int, high: int) -> int:
    raw = req.arg(name)
    if raw in (None, ""):
        return default
    try:
        return max(low, min(high, int(raw)))
    except ValueError:
        raise HttpError(400, f"{name} deve ser inteiro") from None


class BoundedCache:
    """Dicionário com lock e limite: várias threads HTTP leem e gravam; o mais antigo sai primeiro."""

    def __init__(self, limit: int = 256):
        self.limit = limit
        self._data: "OrderedDict[str, Any]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self.limit:
                self._data.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


class AgentsService:
    """Índice e observador das sessões de agente, ligados ao ciclo de vida do app."""

    def __init__(self, app):
        self.env = app.env
        self.runner = app.runner
        self.git_cache = repos.GitCache(app.runner)
        self.repos_lock = threading.Lock()
        self.store = app.store
        self.app = app
        self._context_cache = BoundedCache(256)
        self._pairs_cache: tuple = (None, {})
        self._pairs_lock = threading.Lock()
        self.index = AgentIndex(index_path(app.data_dir))
        self.watcher = AgentWatcher(self.index, self.env)

    def start(self) -> None:
        if self.env.get("VULCAN_AGENTS") != "0":
            self.watcher.start()

    def stop(self) -> None:
        self.watcher.stop()
        self.index.close()

    def refresh(self) -> List[str]:
        return self.watcher.run_once()

    # ── pareamento com as abas ───────────────────────────────────
    def pairs(self) -> Dict[str, Dict]:
        """Pares sessão de agente -> aba; refeito só quando índice, abas ou arquivos do hook mudam."""
        folder = pairing.pairings_dir(self.app.data_dir)
        try:
            folder_mtime = folder.stat().st_mtime
        except OSError:
            folder_mtime = 0
        tabs = self.app.hub.sessions.list("*")
        key = (self.index.revision(), folder_mtime, tuple((t.id, len(t.commands), t.theme) for t in tabs))
        with self._pairs_lock:
            if self._pairs_cache[0] != key:
                self._pairs_cache = (key, pairing.resolve(self.index.sessions(), tabs, pairing.read_pairings(folder)))
            return self._pairs_cache[1]

    def decorate(self, sessions: List[AgentSession]) -> List[AgentSession]:
        heard = attention_hook.read_records(attention_hook.attention_dir(self.app.data_dir))
        for s in sessions:
            s.attention_hook = heard.get(s.id)
        return pairing.apply(sessions, self.pairs())

    def paired_with(self, terminal_id: str) -> Optional[AgentSession]:
        """A sessão de agente mais recente pareada com a aba."""
        for s in self.decorate(self.index.sessions()):  # da mais recente para a mais antiga
            if s.pairing_id == terminal_id:
                return s
        return None

    # ── sessão atual ─────────────────────────────────────────────
    def chosen_id(self) -> Optional[str]:
        data = self.store.load("agents_current", {})
        value = data.get("session_id") if isinstance(data, dict) else None
        return value if isinstance(value, str) else None

    def choose(self, session_id: Optional[str]) -> None:
        self.store.save("agents_current", {"session_id": session_id})

    def context(self, session: Optional[AgentSession]) -> Dict[str, str]:
        """Contexto dos prompts com cache de 30 s por sessão: a barra se atualiza sem rodar git toda vez."""
        if session is None:
            return {}
        key = f"{session.id}|{session.cwd}|{session.git_branch}"
        hit = self._context_cache.get(key)
        if hit and time.monotonic() - hit[0] < CONTEXT_TTL:
            return hit[1]
        ctx = prompts.context_for(session, self.runner)
        self._context_cache.put(key, (time.monotonic(), ctx))
        return ctx

    def harness_line(self, s: AgentSession) -> Optional[Dict[str, str]]:
        """Resumo de uma linha do harness do projeto da sessão, com o site para o link da aba."""
        key = f"harness:{s.project_root or s.cwd}"
        cached = self._context_cache.get(key)
        if cached and time.monotonic() - cached[0] < CONTEXT_TTL:
            return cached[1]  # a lista de sites passa pelo Lerd: 30 s de cache por pasta
        value = self._harness_line(s)
        self._context_cache.put(key, (time.monotonic(), value))
        return value

    def _harness_line(self, s: AgentSession) -> Optional[Dict[str, str]]:
        try:
            site = harness.find_project(s.project_root or s.cwd, self.app.sites())
        except Exception:  # noqa: BLE001  backend fora do ar: a sessão abre sem o resumo
            return None
        if site is None:
            return None
        line = harness.summary(harness.read(site.path))
        return {"site": site.name, "line": line} if line else None

    def current_session(self) -> Optional[AgentSession]:
        return prompts.choose_current(self.decorate(self.index.sessions()), self.chosen_id())

    def current(self) -> Dict[str, Any]:
        session = self.current_session()
        chosen = self.chosen_id()
        return {"session": card(session) if session else None, "automatic": not (session and session.id == chosen),
                "context": self.context(session)}


ATTENTION_LIMIT = 50


def clean_line(value: Any) -> str:
    return " ".join(str(value).split())[:160] if isinstance(value, str) else ""


def register_agents_api(app) -> AgentsService:
    srv = app.server
    service = AgentsService(app)

    @srv.route("GET", "/api/agents/revision")
    def revision(_req: Request):
        return {"revision": service.index.revision(), "last_scan": service.watcher.last_scan,
                "last_error": service.watcher.last_error}

    @srv.route("GET", "/api/agents/attention")
    def attention_items(_req: Request):
        """Sessões que terminaram o turno ou podem estar esperando, para os sinais da interface."""
        items = []
        for s in service.decorate(service.index.sessions()):
            state = attention.resolve(s.attention, hook=s.attention_hook)
            if state and state["state"] != "running":
                items.append({"session": s.id, "agent": s.agent, "project": s.project_name, "terminal_id": s.pairing_id,
                              "state": state["state"], "since": state["since"], "source": state["source"]})
        return {"items": items[:ATTENTION_LIMIT]}

    @srv.route("POST", "/api/agents/notice")
    def notice(req: Request):
        """Aviso do sistema fora da casca do macOS. Texto limitado e passado depois de `--`: não vira opção do comando."""
        body = req.json()
        title, text = clean_line(body.get("title")), clean_line(body.get("text"))
        if not title or sys.platform == "darwin" or not shutil.which("notify-send"):
            return {"sent": False}
        app.runner.run(["notify-send", "--", title, text], timeout=5)
        return {"sent": True}

    @srv.route("GET", "/api/agents/sessions")
    def sessions(req: Request):
        all_sessions = service.decorate(service.index.sessions())
        chosen = [s for s in all_sessions if matches(s, req)]
        projects: Dict[str, int] = {}
        for s in all_sessions:
            if s.project_name:  # sessão sem pasta: um nome vazio no filtro viraria "Todos os projetos"
                projects[s.project_name] = projects.get(s.project_name, 0) + 1
        today = datetime.now().astimezone().date().isoformat()
        edited_today = service.index.edited_on_day(today, None if len(chosen) == len(all_sessions) else [s.id for s in chosen])
        return {"sessions": [card(s) for s in chosen], "kpis": kpis(chosen, today, edited_today), "total": len(all_sessions),
                "projects": [{"name": k, "count": v} for k, v in sorted(projects.items(), key=lambda kv: (-kv[1], kv[0]))],
                "revision": service.index.revision(), "roots": service.watcher.roots()}

    @srv.route("GET", rf"/api/agents/sessions/{SESSION_ID}")
    def session(req: Request):
        s = service.index.session(req.params["sid"])
        if not s:
            raise HttpError(404, "sessão de agente não encontrada")
        service.decorate([s])
        start = _int(req, "from", 0, 0, 10 ** 9)
        limit = _int(req, "limit", 200, 1, 1000)
        events, nxt = service.index.events(s.id, start, limit)
        data = detail(s)
        rows = service.index.usage_rows(session_id=s.id)
        table, _ = pricing.load(service.app.data_dir)
        costs = [pricing.cost(r, table) for r in rows]
        known = [c for c in costs if c is not None]
        # custo estimado da sessão no preço da API: None sem nenhum turno com preço
        data["cost"] = {"value": round(sum(known), 6) if known else None, "partial": bool(known) and len(known) < len(costs),
                        "turns": len(rows)}
        data["harness"] = service.harness_line(s)
        return {"session": data, "events": [e.__dict__ for e in events], "next": nxt,
                "revision": service.index.revision()}

    @srv.route("GET", "/api/agents/history")
    def history_search(req: Request):
        kind = req.arg("kind") or None
        if kind and kind not in KINDS:
            raise HttpError(400, "kind deve ser pedidos, respostas, comandos ou arquivos")
        hits = service.index.search(req.arg("q") or "", kind, req.arg("agent") or None, req.arg("project") or None,
                                    _int(req, "limit", 100, 1, 500))
        return {"hits": hits, "fts": service.index.fts, "revision": service.index.revision(),
                "claude_cleanup": claude_cleanup_days(discovery.claude_root(service.env))}

    def usage_report(req: Request, default_group: str = "day") -> Dict[str, Any]:
        """Tokens e custo estimado por grupo no período (dias locais), com o total."""
        group = req.arg("group") or default_group
        if group not in usage.GROUPS:
            raise HttpError(400, f"group deve ser {', '.join(usage.GROUPS)}")
        try:
            start, end = usage.period(req.arg("from"), req.arg("to"))
        except ValueError as exc:
            raise HttpError(400, str(exc)) from None
        since, until = usage.utc_bounds(start, end)
        revision = service.index.revision()  # antes dos dados: uma gravação no meio faz a tela ler de novo
        table, warning = pricing.load(service.app.data_dir)
        report = usage.aggregate(service.index.usage_rows(since, until), table, group, start, end)
        report["prices_warning"] = warning
        report["revision"] = revision
        report["scanned"] = service.watcher.settled()  # antes da 1a varredura terminar o índice está incompleto
        return report

    service.usage_report = usage_report

    @srv.route("GET", "/api/agents/usage")
    def usage_json(req: Request):
        return usage_report(req)

    @srv.route("GET", r"/api/agents/usage\.csv")
    def usage_csv(req: Request):
        report = usage_report(req, "session")
        name = f"uso-agentes-{report['group']}-{report['from']}-{report['to']}.csv"
        return RawResponse(usage.to_csv(report).encode("utf-8"), "text/csv; charset=utf-8", name)

    @srv.route("GET", "/api/agents/repos")
    def repo_states(req: Request):
        # git só leitura, com timeout por comando e cache de 30 s por pasta; uma montagem por vez
        with service.repos_lock:
            if req.arg("fresh") in ("1", "true"):
                service.git_cache.clear()  # botão Atualizar
            projects = repos.build(service.index.sessions(), service.git_cache)
        return {"projects": projects, "revision": service.index.revision()}

    @srv.route("POST", rf"/api/agents/sessions/{SESSION_ID}/resume")
    def resume(req: Request):
        """Retoma a sessão numa aba nova: pasta da sessão, tema da aba pareada (ou o próximo da rotação) e o comando
        do agente digitado. O id vem do índice e passa pelo padrão SESSION_ID; nada do cliente vira comando."""
        sid = req.params["sid"]
        s = service.index.session(sid)
        if s is None:
            raise HttpError(404, "sessão de agente não encontrada")
        service.decorate([s])
        folder = next((p for p in (s.cwd, s.project_root) if p and Path(p).is_dir()), None)
        if folder is None:
            raise HttpError(409, "a pasta da sessão não existe mais nesta máquina")
        typed = RESUME_COMMANDS[s.agent].format(id=s.id)
        theme = s.theme if themes.is_theme(s.theme) else app.theme_rotation.take()
        session = app.spawn_terminal(folder, s.project_name or Path(folder).name, theme, typed=typed)
        return 201, session.info()

    @srv.route("GET", "/api/agents/paired")
    def paired(req: Request):
        terminal = req.arg("terminal") or ""
        s = service.paired_with(terminal) if terminal else None
        alive = bool(s) and procinfo.tab_runs_agent(service.app.terminals.get(terminal), s.agent)
        return {"session": card(s) if s else None, "alive": alive}

    @srv.route("GET", "/api/agents/current")
    def current(_req: Request):
        return service.current()

    @srv.route("PUT", "/api/agents/current")
    def choose_current(req: Request):
        session_id = req.json().get("session_id")
        if session_id is not None and not isinstance(session_id, str):
            raise HttpError(400, "session_id deve ser texto ou null")
        if session_id is not None and service.index.session(session_id) is None:
            raise HttpError(404, "sessão de agente não encontrada")
        service.choose(session_id)
        return service.current()

    @srv.route("POST", "/api/agents/refresh")
    def refresh(_req: Request):
        return {"changed": service.refresh(), "revision": service.index.revision()}

    return service
