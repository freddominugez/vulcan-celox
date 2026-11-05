"""Server application: wires the core (backend, notebook, terminals) to the HTTP routes."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from vulcan_celox import APP_NAME, __version__
from vulcan_celox.core import paths, themes
from vulcan_celox.core.backends import detect_backend
from vulcan_celox.core.i18n import tr
from vulcan_celox.core.oscompat import is_windows, open_argv
from vulcan_celox.core.notebook import Notebook
from vulcan_celox.core.progress import progress, progress_by_site
from vulcan_celox.core.pty_session import TerminalManager
from vulcan_celox.core.store import Store, migrate_legacy, secure_data_dir
from vulcan_celox.core import i18n
from vulcan_celox.core.backup import apply_pending_restore
from vulcan_celox.server.autostart import failure_reason, wait_running
from vulcan_celox.server.local_http import HttpError, LocalServer, Request

SERVICE_ACTIONS = ("start", "stop", "restart")
NEW_TERMINAL_AGENTS = ("shell", "claude", "codex")
MIN_TOKEN = 32  # VULCAN_TOKEN vindo do ambiente (a casca gera 64 caracteres)
PACKAGE_SUFFIXES = (".app", ".pkg", ".mpkg")  # "opening" a package in Finder runs the program


def site_payload(site) -> Dict[str, Any]:
    path = Path(site.path) if site.path else None
    return {
        "name": site.name, "domain": site.domain, "url": site.url, "path": site.path, "kind": site.kind,
        "secured": site.secured, "php": site.php, "node": site.node,
        "exists": bool(path and path.is_dir()),
        "has_artisan": bool(path and (path / "artisan").is_file()),
        "has_composer": bool(path and (path / "composer.json").is_file()),
        "has_package_json": bool(path and (path / "package.json").is_file()),
    }


# what Settings can hide; Settings itself stays, or there would be no way back
SIDEBAR_ITEMS = frozenset({
    "inicio", "overview", "node", "terminals", "ambiente", "depuracao", "agentes", "prompts", "agentes-uso",
    "agentes-branches", "agentes-historico", "tasks", "notes", "tags", "index", "ajuda",
    "section-sessions", "section-sites", "section-node",
})


def valid_sidebar_hidden(value: Any) -> List[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item in SIDEBAR_ITEMS for item in value):
        raise HttpError(400, "sidebar_hidden deve ser uma lista de itens da barra lateral")
    return sorted(set(value))


class VulcanApp:
    def __init__(self, env: Optional[Mapping[str, str]] = None, runner=None, token: Optional[str] = None,
                 port: int = 0, keystore=None, ai_transport=None):
        self.env = dict(os.environ if env is None else env)
        paths.migrate_data_folder(self.env)
        self.data_dir = paths.data_dir(self.env)
        apply_pending_restore(self.data_dir)  # before anything reads the data
        secure_data_dir(self.data_dir)  # 0700/0600: agent memories and events readable by the user only
        self.store = Store(self.data_dir)
        i18n.set_language(i18n.resolve(self.store.load("preferences", {}), self.env))
        migrate_legacy(self.store, paths.legacy_dir(self.env))
        self.notebook = Notebook(self.store)
        self.notebook.migrate_legacy_notes()
        self.backend = detect_backend(self.env, runner=runner)
        self.runner = self.backend.runner
        self._service_lock = threading.Lock()
        from vulcan_celox.core.keychain import MemoryKeyStore, default_keystore
        # VULCAN_KEYSTORE=memory: isolated runs (captures, validation) never touch the real Keychain
        self.keystore = keystore or (MemoryKeyStore() if self.env.get("VULCAN_KEYSTORE") == "memory"
                                     else default_keystore(runner=self.runner))
        self.ai_transport = ai_transport  # None: urllib de verdade
        from vulcan_celox.server.autostart import EnvAutostart
        self.autostart = EnvAutostart(self)
        env_token = self.env.get("VULCAN_TOKEN")
        if token is None and env_token is not None and len(env_token) < MIN_TOKEN:
            raise ValueError(f"VULCAN_TOKEN precisa ter pelo menos {MIN_TOKEN} caracteres")
        self.server = LocalServer(port=port, token=token or env_token)
        self.terminals = TerminalManager(self.env)
        self.theme_rotation = themes.Rotation(self.store)
        from vulcan_celox.server.session_hub import SessionHub
        self.hub = SessionHub(self)
        self._register_core_routes()
        from vulcan_celox.server.terminals_api import register_terminal_api
        register_terminal_api(self)
        from vulcan_celox.server.notebook_api import NotebookApi
        from vulcan_celox.server.sessions_api import register_sessions_api
        self.notebook_api = NotebookApi(self)
        register_sessions_api(self)
        from vulcan_celox.server.ai_api import register_ai_config_api
        self.ai = register_ai_config_api(self)
        from vulcan_celox.server.fs_api import register_fs_api
        register_fs_api(self)
        from vulcan_celox.server.ai_docs import register_ai_docs_api
        self.ai_docs = register_ai_docs_api(self)
        from vulcan_celox.server.agents_api import register_agents_api
        self.agents = register_agents_api(self)
        from vulcan_celox.server.prompts_api import register_prompts_api
        self.prompts = register_prompts_api(self)
        from vulcan_celox.server.code_api import register_code_api
        self.code = register_code_api(self)
        from vulcan_celox.server.pr_api import register_pr_api
        register_pr_api(self)
        from vulcan_celox.server.sites_api import register_sites_api
        register_sites_api(self)
        from vulcan_celox.server.env_api import register_env_api
        register_env_api(self)
        from vulcan_celox.server.debug_api import register_debug_api
        register_debug_api(self)
        from vulcan_celox.server.node_api import register_node_api
        self.node = register_node_api(self)
        from vulcan_celox.server.guide_api import register_guide_api
        register_guide_api(self)
        from vulcan_celox.server.data_api import register_data_api
        register_data_api(self)

    # ── dados ────────────────────────────────────────────────────────────
    def manual_sites(self) -> Dict[str, str]:
        data = self.store.load("sites", {})
        return data if isinstance(data, dict) else {}

    def sites(self):
        return self.backend.list_sites(self.manual_sites())

    def favorites(self) -> List[str]:
        data = self.store.load("favorites", [])
        return [x for x in data if isinstance(x, str)] if isinstance(data, list) else []

    def site(self, name: Optional[str]):
        if not name:
            return None
        return next((s for s in self.sites() if s.name == name), None)

    def refresh_backend(self) -> None:
        """Lerd installed while the app is open is noticed without restarting."""
        if not self.backend.available:
            self.backend = detect_backend(self.env, runner=self.runner)

    def state(self) -> Dict[str, Any]:
        self.refresh_backend()
        status = self.backend.status()
        by_site = progress_by_site(self.notebook.tasks)
        overall = progress(self.notebook.tasks)
        return {
            "app": {"name": APP_NAME, "version": __version__, "data_dir": str(self.data_dir)},
            "backend": {
                "name": self.backend.name, "label": self.backend.label, "available": self.backend.available,
                "installable": not is_windows(),
                "dashboard": self.backend.dashboard_url() if hasattr(self.backend, "dashboard_url") else None,
            },
            "status": {"running": status.running, "summary": status.summary, "details": status.details},
            "autostart": self.autostart.state(),
            "sites": [site_payload(s) for s in self.sites()],
            "favorites": self.favorites(),
            "progress": {
                "overall": {"total": overall.total, "done": overall.done, "pct": overall.pct, "label": overall.label},
                "sites": {("" if k is None else k): {"total": p.total, "done": p.done, "pct": p.pct, "label": p.label}
                          for k, p in by_site.items()},
            },
        }

    # ── new terminal ─────────────────────────────────────────
    def spawn_terminal(self, cwd: str, title: str, theme: Optional[str], site: Optional[str] = None,
                       rows: int = 30, cols: int = 110, command: Optional[str] = None, typed: Optional[str] = None):
        """Creates the tab, registers the session and, if `typed` is given, types the command (agent) as soon as the shell starts.
        The shell buffers what arrives before it is ready; the command goes into the tab record for pairing by
        folder and time. `typed` is always built by the server from validated values."""
        session = self.terminals.create(cwd, command=command, title=title[:60], site=site, rows=rows, cols=cols,
                                        theme=theme)
        self.hub.on_created(session)
        if typed:
            session.write(f"{typed}\r".encode())  # same as the keyboard Enter: in PowerShell, \n only opens another line
            self.hub.sessions.add_commands(session.id, [typed])
        return session

    def new_terminal_prefs(self) -> Dict[str, Any]:
        data = self.store.load("new_terminal", {})
        data = data if isinstance(data, dict) else {}
        agent = data.get("agent")
        return {"skip_folder": data.get("skip_folder") is True,
                "agent": agent if agent in NEW_TERMINAL_AGENTS else "shell"}

    def save_new_terminal_prefs(self, value) -> None:
        if not isinstance(value, dict):
            raise HttpError(400, "new_terminal deve ser um objeto")
        prefs = self.new_terminal_prefs()
        if "skip_folder" in value:
            if not isinstance(value["skip_folder"], bool):
                raise HttpError(400, "skip_folder deve ser verdadeiro ou falso")
            prefs["skip_folder"] = value["skip_folder"]
        if "agent" in value:
            if value["agent"] not in NEW_TERMINAL_AGENTS:
                raise HttpError(400, "agent deve ser claude, codex ou shell")
            prefs["agent"] = value["agent"]
        self.store.save("new_terminal", prefs)

    # ── rotas ────────────────────────────────────────────────────────────
    def _register_core_routes(self) -> None:
        srv = self.server

        @srv.route("GET", "/api/state")
        def _state(_req: Request):
            return self.state()

        @srv.route("POST", r"/api/services/(?P<action>[a-z]+)")
        def _service(req: Request):
            action = req.params["action"]
            if action not in SERVICE_ACTIONS:
                raise HttpError(404, "ação desconhecida")
            if not self.backend.available:
                raise HttpError(409, "nenhum ambiente (Lerd ou Valet) disponível")
            if not self._service_lock.acquire(blocking=False):
                raise HttpError(409, "outra operação de serviço está em andamento")
            try:
                result = getattr(self.backend, action)()
                status = wait_running(self.backend, self.autostart.start_wait) if result.ok and action != "stop" else None
            finally:
                self._service_lock.release()
            lines = (result.output or "").strip().splitlines()
            if status is not None and not status.running:
                reason = tr("o comando terminou, mas o ambiente não respondeu: {summary}", summary=status.summary)
                return {"ok": False, "code": result.code, "output": "\n".join(lines[-40:] + [reason])}
            detail = lines[-40:] if result.ok else lines[-40:] + [failure_reason(result)]
            return {"ok": result.ok, "code": result.code, "output": "\n".join(detail)}

        @srv.route("GET", "/api/app/build")
        def _build(_req: Request):
            loaded, installed = srv.build_id, srv.disk_build_id()
            return {"version": __version__, "loaded": loaded, "installed": installed, "outdated": loaded != installed}

        @srv.route("PATCH", "/api/preferences")
        def _preferences(req: Request):
            body = req.json()
            if "autostart_env" in body:
                if not isinstance(body["autostart_env"], bool):
                    raise HttpError(400, "autostart_env deve ser verdadeiro ou falso")
                self.autostart.set_enabled(body["autostart_env"])
            if "new_terminal" in body:
                self.save_new_terminal_prefs(body["new_terminal"])
            prefs = self.store.load("preferences", {})
            if not isinstance(prefs, dict):
                prefs = {}
            if "attention_notify" in body:
                if not isinstance(body["attention_notify"], bool):
                    raise HttpError(400, "attention_notify deve ser verdadeiro ou falso")
                prefs["attention_notify"] = body["attention_notify"]
                self.store.save("preferences", prefs)
            if "theme" in body:
                if body["theme"] not in ("sistema", "claro", "escuro"):
                    raise HttpError(400, "theme deve ser sistema, claro ou escuro")
                prefs["theme"] = body["theme"]
                self.store.save("preferences", prefs)
            if "language" in body:
                if body["language"] not in i18n.LANGUAGES:
                    raise HttpError(400, "language deve ser en ou pt")
                prefs["language"] = body["language"]
                self.store.save("preferences", prefs)
                i18n.set_language(i18n.resolve(prefs, self.env))
            if "sidebar_hidden" in body:
                prefs["sidebar_hidden"] = valid_sidebar_hidden(body["sidebar_hidden"])
                self.store.save("preferences", prefs)
            if "pr_status" in body:
                if not isinstance(body["pr_status"], bool):
                    raise HttpError(400, "pr_status deve ser verdadeiro ou falso")
                prefs["pr_status"] = body["pr_status"]
                self.store.save("preferences", prefs)
            return {"autostart": self.autostart.state(), "new_terminal": self.new_terminal_prefs(),
                    "attention_notify": prefs.get("attention_notify", True), "pr_status": prefs.get("pr_status", False),
                    "theme": prefs.get("theme", "sistema"), "language": i18n.language(),
                    "sidebar_hidden": prefs.get("sidebar_hidden", []), "data_dir": str(self.data_dir), "version": __version__}

        @srv.route("GET", "/api/i18n")
        def _i18n(_req: Request):
            lang = i18n.language()
            return {"language": lang, "dictionary": i18n.dictionary() if lang != "pt" else {}}

        @srv.route("POST", "/api/open")
        def _open(req: Request):
            body = req.json()
            kind, target = body.get("kind"), str(body.get("target") or "")
            if kind == "url":
                if not target.startswith(("http://", "https://")):
                    raise HttpError(400, "URL precisa começar com http:// ou https://")
                argv = open_argv("url", target, self.env)
            elif kind == "dashboard":
                if not hasattr(self.backend, "dashboard_url"):
                    raise HttpError(409, "painel indisponível para este backend")
                argv = open_argv("url", self.backend.dashboard_url(), self.env)
            elif kind == "finder":
                if not Path(target).is_dir():
                    raise HttpError(400, "pasta não existe")
                if Path(target).resolve().name.lower().endswith(PACKAGE_SUFFIXES):
                    raise HttpError(400, "pacotes de aplicativo não são abertos por aqui")
                argv = open_argv("folder", target, self.env)
            elif kind == "editor":
                if not Path(target).is_dir():
                    raise HttpError(400, "pasta não existe")
                argv = open_argv("editor", target, self.env)
            elif kind == "prompt":
                from vulcan_celox.server.prompts_api import is_prompt_file
                if not is_prompt_file(Path(target), self.prompts.global_dir):
                    raise HttpError(400, "só arquivos de prompt (.md da pasta de prompts) podem ser abertos assim")
                argv = open_argv("editor", str(Path(target).resolve()), self.env)
            elif kind == "source":
                # source file of a debug event, only if it is inside a registered site
                path = Path(os.path.abspath(target))
                roots = [Path(os.path.abspath(s.path)) for s in self.sites() if s.path]
                if not path.is_file() or not any(r in path.parents for r in roots):
                    raise HttpError(400, "só arquivos que existem dentro de um site podem ser abertos assim")
                argv = open_argv("editor", str(path), self.env)
            elif kind == "file":
                data_dir = Path(self.data_dir).resolve()
                path = Path(target).resolve()
                try:
                    path.relative_to(data_dir)
                except ValueError:
                    raise HttpError(400, "só arquivos da pasta de dados do Vulcan Celox podem ser abertos") from None
                if not path.is_file():
                    raise HttpError(404, "arquivo não encontrado")
                if path.suffix.lower() != ".md":
                    raise HttpError(400, "só arquivos .md da pasta de dados podem ser abertos assim")
                argv = open_argv("file", str(path), self.env)
            elif kind == "session_file":
                # code viewer: same check as reading, including the session root and sensitive names
                path = self.code.checked(self.code.session(str(body.get("session") or "")), target)
                if not path.is_file():
                    raise HttpError(404, "arquivo não encontrado")
                argv = open_argv("editor", str(path), self.env)
            elif kind == "terminal_file":
                # path clicked in the terminal: the server checks again, never what the page claims
                found = self.code.resolve(str(body.get("terminal") or ""), [target]).get(target)
                if not found or found["kind"] != "file" or found["sensitive"]:
                    raise HttpError(403, "este arquivo não pode ser aberto")
                argv = open_argv("editor", found["path"], self.env)
            else:
                raise HttpError(400, "kind deve ser url, dashboard, finder, editor, file, prompt, source, session_file ou terminal_file")
            result = self.runner.run(argv, timeout=15)
            if not result.ok:
                raise HttpError(500, (result.output or tr("falha ao abrir")).strip())
            return {"ok": True}

    # ── execution ──────────────────────────────────────────────────────
    def start(self) -> "VulcanApp":
        self.server.start()
        self.agents.start()
        return self

    def shutdown(self) -> None:
        self.notebook_api.flush_index()
        self.hub.finalize_all()  # saves the memory of every open session before killing the PTYs
        self.terminals.close_all()
        self.hub.stop()
        self.server.shutdown()  # stops accepting requests before closing the agents database
        self.agents.stop()


def _watch_parent(parent_pid: int, shutdown=None, getppid=os.getppid, exit=os._exit, interval: float = 1.0,
                  grace: float = 3.0) -> None:
    """Native app exited (even abnormally): saves memories and closes the tabs within a deadline, then exits leaving
    no orphaned server or PTYs."""
    while True:
        time.sleep(interval)
        if getppid() != parent_pid:
            break
    if shutdown is not None:
        worker = threading.Thread(target=shutdown, name="vigia-encerra", daemon=True)
        worker.start()
        worker.join(timeout=grace)
    exit(0)


def _raise_interrupt(_signum, _frame):
    raise KeyboardInterrupt


def serve(port: int = 0) -> int:
    import signal
    app = VulcanApp(port=port)
    # the native app exits with SIGTERM: treat it as an interrupt so memories and index get saved
    signal.signal(signal.SIGTERM, _raise_interrupt)
    sys.stdout.write(f"VULCAN_PORT={app.server.port}\n")
    sys.stdout.flush()
    app.autostart.begin()  # the environment starts with the app, without delaying the window
    app.agents.start()  # serve_forever does not go through start(): the agent watcher starts here
    if os.environ.get("VULCAN_WATCH_PARENT") == "1":
        threading.Thread(target=_watch_parent, args=(os.getppid(), app.shutdown), daemon=True).start()
    try:
        app.server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.shutdown()
    return 0
