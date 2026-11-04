"""Início guide: steps checked against the app state, the choice to skip the guide, and the optional Lerd step.

Nothing here changes the environment: it only reads what the app already knows and stores `guide` in the Store.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from vulcan_celox.core.i18n import tr
from vulcan_celox.core.oscompat import is_windows
from vulcan_celox.server.local_http import HttpError, Request

STORE_KEY = "guide"
# the official installer (lerd.sh). It runs only in a visible terminal, after the user has read it and confirmed
LERD_INSTALL = "curl -fsSL https://lerd.sh/install.sh | bash"


def register_guide_api(app) -> None:
    srv = app.server

    def saved() -> Dict[str, Any]:
        data = app.store.load(STORE_KEY, {})
        return data if isinstance(data, dict) else {}

    def lerd_step() -> List[Dict[str, Any]]:
        """Optional: it never holds the guide back, and it does not exist on Windows."""
        if is_windows():
            return []
        status = app.backend.status()
        installed = bool(app.backend.available)
        running = bool(installed and status.running)
        skipped = bool(saved().get("lerd_skipped"))
        failure = app.autostart.state()
        if running:
            detail = status.summary
        elif skipped:
            detail = tr("Você marcou que não usa. Terminais, agentes e projetos Node funcionam sem ele.")
        elif installed and failure.get("phase") == "failed":
            detail = failure.get("message") or status.summary
        elif installed:
            detail = tr("Instalado e desligado. Só é preciso para rodar sites PHP e Laravel.")
        else:
            detail = tr("Só é preciso para rodar sites PHP e Laravel. Projetos Node, terminais e agentes funcionam sem ele.")
        label = app.backend.label if installed else "Lerd"
        return [{"id": "lerd", "ok": running, "optional": True, "state": "running" if running else "stopped" if installed else "absent",
                 "skipped": skipped and not running, "autostart": failure.get("enabled", False), "install_command": LERD_INSTALL,
                 "title": tr("{label} (opcional)", label=label), "detail": detail}]

    def steps() -> List[Dict[str, Any]]:
        app.refresh_backend()
        sites = len(app.sites())
        node = len(app.node.saved()) if getattr(app, "node", None) else 0
        try:
            counts = app.agents.index.counts() if getattr(app, "agents", None) else {}
        except Exception:  # noqa: BLE001 (index still opening: the step just stays pending)
            counts = {}
        agents = int(counts.get("claude", 0)) + int(counts.get("codex", 0))
        watcher = getattr(getattr(app, "agents", None), "watcher", None)
        reading = bool(watcher is not None and not agents and not watcher.settled())
        opened = bool(app.terminals.list()) or bool(app.hub.sessions.list("*")) or bool(saved().get("first_terminal"))
        return [
            *lerd_step(),
            {"id": "projetos", "ok": sites + node > 0, "title": tr("Encontrar seus projetos"),
             "detail": tr("{sites} site(s) PHP e {node} projeto(s) Node", sites=sites, node=node) if sites + node else tr("Registre um site no Lerd ou adicione a pasta de um projeto Node.")},
            {"id": "agentes", "ok": agents > 0, "lendo": reading, "title": tr("Ler as sessões dos agentes"),
             "detail": tr("{agents} sessão(ões) do Claude Code e do Codex, só leitura", agents=agents) if agents
             else tr("Lendo as sessões do Claude Code e do Codex...") if reading
             else tr("Nenhuma sessão ainda. Use o Claude Code ou o Codex numa pasta de projeto.")},
            {"id": "terminal", "ok": opened, "title": tr("Abrir o primeiro terminal num projeto"),
             "detail": tr("Feito. Cada terminal guarda tarefas e notas da sessão.") if opened else tr("⌘T abre um terminal; as tarefas e notas dele viram memória em Markdown.")},
        ]

    def payload() -> Dict[str, Any]:
        items = steps()
        data = saved()
        if any(s["id"] == "terminal" and s["ok"] for s in items) and not data.get("first_terminal"):
            data["first_terminal"] = True
            app.store.save(STORE_KEY, data)
        done = all(s["ok"] for s in items if not s.get("optional"))
        return {"steps": items, "done": done, "skipped": bool(data.get("skipped")),
                "show_on_open": not done and not data.get("skipped")}

    @srv.route("GET", "/api/guide")
    def get_guide(req: Request):
        return payload()

    @srv.route("PUT", "/api/guide")
    def put_guide(req: Request):
        body = req.json()
        fields = {key: body[key] for key in ("skipped", "lerd_skipped") if key in body}
        if not fields or not all(isinstance(value, bool) for value in fields.values()):
            raise HttpError(400, "skipped deve ser verdadeiro ou falso")
        data = saved()
        data.update(fields)
        app.store.save(STORE_KEY, data)
        return payload()

    @srv.route("POST", "/api/guide/lerd/install")
    def install_lerd(req: Request):
        if is_windows():
            raise HttpError(409, "o Lerd não roda direto no Windows")
        home = app.env.get("HOME") or str(Path.home())
        session = app.spawn_terminal(home, tr("Instalar o Lerd"), None, command=LERD_INSTALL)
        return 201, session.info()
