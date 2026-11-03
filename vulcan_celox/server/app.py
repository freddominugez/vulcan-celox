"""Aplicação do servidor: liga núcleo (backend, caderno, terminais) às rotas HTTP."""

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
from vulcan_celox.core.oscompat import open_argv
from vulcan_celox.core.notebook import Notebook
from vulcan_celox.core.progress import progress, progress_by_site
from vulcan_celox.core.pty_session import TerminalManager
from vulcan_celox.core.store import Store, migrate_legacy, secure_data_dir
from vulcan_celox.core import i18n
from vulcan_celox.server.local_http import HttpError, LocalServer, Request

SERVICE_ACTIONS = ("start", "stop", "restart")
NEW_TERMINAL_AGENTS = ("shell", "claude", "codex")
MIN_TOKEN = 32  # VULCAN_TOKEN vindo do ambiente (a casca gera 64 caracteres)
PACKAGE_SUFFIXES = (".app", ".pkg", ".mpkg")  # "abrir" um pacote no Finder executa o programa


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


class VulcanApp:
    def __init__(self, env: Optional[Mapping[str, str]] = None, runner=None, token: Optional[str] = None,
                 port: int = 0, keystore=None, ai_transport=None):
        self.env = dict(os.environ if env is None else env)
        self.data_dir = paths.data_dir(self.env)
        secure_data_dir(self.data_dir)  # 0700/0600: memórias e eventos dos agentes só do usuário
        self.store = Store(self.data_dir)
        i18n.set_language(i18n.resolve(self.store.load("preferences", {}), self.env))
        migrate_legacy(self.store, paths.legacy_dir(self.env))
        self.notebook = Notebook(self.store)
        self.notebook.migrate_legacy_notes()
        self.backend = detect_backend(self.env, runner=runner)
        self.runner = self.backend.runner
        self._service_lock = threading.Lock()
        from vulcan_celox.core.keychain import MemoryKeyStore, default_keystore
        # VULCAN_KEYSTORE=memory: execuções isoladas (capturas, validação) nunca tocam o Keychain real
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

    def state(self) -> Dict[str, Any]:
        status = self.backend.status()
        by_site = progress_by_site(self.notebook.tasks)
        overall = progress(self.notebook.tasks)
        return {
            "app": {"name": APP_NAME, "version": __version__, "data_dir": str(self.data_dir)},
            "backend": {
                "name": self.backend.name, "label": self.backend.label, "available": self.backend.available,
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

    # ── novo terminal ─────────────────────────────────────────
    def spawn_terminal(self, cwd: str, title: str, theme: Optional[str], site: Optional[str] = None,
                       rows: int = 30, cols: int = 110, command: Optional[str] = None, typed: Optional[str] = None):
        """Cria a aba, registra a sessão e, se `typed` vier, digita o comando (agente) assim que o shell nascer.
        O shell guarda o que chega antes de ficar pronto; o comando entra no registro da aba para o pareamento por
        pasta e horário. `typed` é sempre montado pelo servidor a partir de valores validados."""
        session = self.terminals.create(cwd, command=command, title=title[:60], site=site, rows=rows, cols=cols,
                                        theme=theme)
        self.hub.on_created(session)
        if typed:
            session.write(f"{typed}\n".encode())
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
            finally:
                self._service_lock.release()
            lines = (result.output or "").strip().splitlines()
            return {"ok": result.ok, "code": result.code, "output": "\n".join(lines[-40:])}

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
            if "pr_status" in body:
                if not isinstance(body["pr_status"], bool):
                    raise HttpError(400, "pr_status deve ser verdadeiro ou falso")
                prefs["pr_status"] = body["pr_status"]
                self.store.save("preferences", prefs)
            return {"autostart": self.autostart.state(), "new_terminal": self.new_terminal_prefs(),
                    "attention_notify": prefs.get("attention_notify", True), "pr_status": prefs.get("pr_status", False),
                    "theme": prefs.get("theme", "sistema"), "language": i18n.language()}

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
                # Arquivo de origem de um evento de depuração, só se estiver dentro de um site registrado
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
                # visor de código: mesma checagem da leitura, inclusive raiz da sessão e nome sensível
                path = self.code.checked(self.code.session(str(body.get("session") or "")), target)
                if not path.is_file():
                    raise HttpError(404, "arquivo não encontrado")
                argv = open_argv("editor", str(path), self.env)
            elif kind == "terminal_file":
                # caminho clicado no terminal: de novo a checagem do servidor, nunca o que a página afirma
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

    # ── execução ─────────────────────────────────────────────────────────
    def start(self) -> "VulcanApp":
        self.server.start()
        self.agents.start()
        return self

    def shutdown(self) -> None:
        self.notebook_api.flush_index()
        self.hub.finalize_all()  # grava a memória de todas as sessões abertas antes de matar os PTYs
        self.terminals.close_all()
        self.hub.stop()
        self.server.shutdown()  # para de aceitar requisições antes de fechar o banco dos agentes
        self.agents.stop()


def _watch_parent(parent_pid: int, shutdown=None, getppid=os.getppid, exit=os._exit, interval: float = 1.0,
                  grace: float = 3.0) -> None:
    """App nativo encerrou (até de forma anormal): grava memórias e fecha as abas com prazo, depois sai sem deixar
    servidor nem PTYs órfãos."""
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
    # o app nativo encerra com SIGTERM: tratar como interrupção para gravar memórias e índice
    signal.signal(signal.SIGTERM, _raise_interrupt)
    sys.stdout.write(f"VULCAN_PORT={app.server.port}\n")
    sys.stdout.flush()
    app.autostart.begin()  # o ambiente sobe junto com o app, sem atrasar a janela
    app.agents.start()  # serve_forever não passa por start(): o observador de agentes sobe aqui
    if os.environ.get("VULCAN_WATCH_PARENT") == "1":
        threading.Thread(target=_watch_parent, args=(os.getppid(), app.shutdown), daemon=True).start()
    try:
        app.server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.shutdown()
    return 0
