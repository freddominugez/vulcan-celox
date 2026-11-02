"""Guia do Início (vt-26 C1): quatro passos que se conferem pelo estado do app, e a escolha de pular o guia.

Nada aqui muda o ambiente: só lê o que o app já sabe e guarda `guide` no Store.
"""

from __future__ import annotations

from typing import Any, Dict, List

from vulcan_terminal.server.local_http import HttpError, Request

STORE_KEY = "guide"


def register_guide_api(app) -> None:
    srv = app.server

    def saved() -> Dict[str, Any]:
        data = app.store.load(STORE_KEY, {})
        return data if isinstance(data, dict) else {}

    def steps() -> List[Dict[str, Any]]:
        status = app.backend.status()
        backend_ok = bool(app.backend.available and status.running)
        sites = len(app.sites())
        node = len(app.node.saved()) if getattr(app, "node", None) else 0
        try:
            counts = app.agents.index.counts() if getattr(app, "agents", None) else {}
        except Exception:  # noqa: BLE001 (índice ainda abrindo: o passo só fica pendente)
            counts = {}
        agents = int(counts.get("claude", 0)) + int(counts.get("codex", 0))
        watcher = getattr(getattr(app, "agents", None), "watcher", None)
        reading = bool(watcher is not None and not agents and not watcher.settled())
        opened = bool(app.terminals.list()) or bool(app.hub.sessions.list("*")) or bool(saved().get("first_terminal"))
        label = app.backend.label if app.backend.available else "Lerd"
        return [
            {"id": "lerd", "ok": backend_ok, "title": f"Ligar o {label}",
             "detail": status.summary if app.backend.available else "Lerd não encontrado. Instale para rodar sites PHP; projetos Node e agentes funcionam sem ele."},
            {"id": "projetos", "ok": sites + node > 0, "title": "Encontrar seus projetos",
             "detail": f"{sites} site(s) PHP e {node} projeto(s) Node" if sites + node else "Registre um site no Lerd ou adicione a pasta de um projeto Node."},
            {"id": "agentes", "ok": agents > 0, "lendo": reading, "title": "Ler as sessões dos agentes",
             "detail": f"{agents} sessão(ões) do Claude Code e do Codex, só leitura" if agents
             else "Lendo as sessões do Claude Code e do Codex..." if reading
             else "Nenhuma sessão ainda. Use o Claude Code ou o Codex numa pasta de projeto."},
            {"id": "terminal", "ok": opened, "title": "Abrir o primeiro terminal num projeto",
             "detail": "Feito. Cada terminal guarda tarefas e notas da sessão." if opened else "⌘T abre um terminal; as tarefas e notas dele viram memória em Markdown."},
        ]

    def payload() -> Dict[str, Any]:
        items = steps()
        data = saved()
        if any(s["id"] == "terminal" and s["ok"] for s in items) and not data.get("first_terminal"):
            data["first_terminal"] = True
            app.store.save(STORE_KEY, data)
        done = all(s["ok"] for s in items)
        return {"steps": items, "done": done, "skipped": bool(data.get("skipped")),
                "show_on_open": not done and not data.get("skipped")}

    @srv.route("GET", "/api/guide")
    def get_guide(req: Request):
        return payload()

    @srv.route("PUT", "/api/guide")
    def put_guide(req: Request):
        body = req.json()
        if not isinstance(body.get("skipped"), bool):
            raise HttpError(400, "skipped deve ser verdadeiro ou falso")
        data = saved()
        data["skipped"] = body["skipped"]
        app.store.save(STORE_KEY, data)
        return payload()
