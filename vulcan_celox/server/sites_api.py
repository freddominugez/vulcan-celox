"""Sites no backend: adicionar, HTTPS, PHP, Node, ações, favoritos, compartilhar e remover."""

from __future__ import annotations

import os
import re
import shlex
import time
from pathlib import Path
from typing import Any, Dict, Tuple

from vulcan_celox.core.laravel_log import read_log
from vulcan_celox.core.oscompat import open_argv
from vulcan_celox.core.pty_session import terminal_env
from vulcan_celox.core.quick_commands import project_commands, recent_commands
from vulcan_celox.core.site_runtime import parse_php_version, parse_which, shim_status
from vulcan_celox.core.trash import move_to_trash
from vulcan_celox.server.local_http import HttpError, Request
from vulcan_celox.server.sites_harness_api import register_site_harness_api

DOMAIN = re.compile(r"^[a-z0-9-]+$")
KINDS = ("link", "park")
RUNTIME_TTL = 30.0
NODE = re.compile(r"^(\d+(\.\d+){0,2}|lts)$")
# domínios dos túneis que o lerd share e o valet share usam; a URL de um --domain próprio vem numa linha de túnel
TUNNEL_SUFFIXES = (".ngrok-free.app", ".ngrok.app", ".ngrok.io", ".ngrok-free.dev", ".trycloudflare.com",
                   ".sharedwithexpose.com", ".expose.dev", ".lhr.life", ".lhr.rocks", ".serveo.net", ".serveousercontent.com",
                   ".pinggy.link", ".pinggy.online", ".a.pinggy.io")
URL = re.compile(r"https://[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?::\d+)?")
TUNNEL_LINE = re.compile(r"forwarding|tunnel|public url|visit it at|shared at|available at", re.IGNORECASE)
NOT_TUNNEL = (".test", "localhost", "127.0.0.1", "ngrok.com", "cloudflare.com", "expose.dev/docs", "lerd.sh")


def extract_public_url(text: str):
    """Primeira URL https do túnel na saída do share, sem códigos de terminal."""
    clean = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text or "")
    fallback = None
    for line in clean.splitlines():
        for url in URL.findall(line):
            host = url[8:].split(":")[0].lower()
            if host.endswith(TUNNEL_SUFFIXES):
                return url
            if fallback is None and TUNNEL_LINE.search(line) and not any(host.endswith(x) or host == x.strip(".")
                                                                        for x in NOT_TUNNEL):
                fallback = url
    return fallback


SITE_ACTIONS = {"db": "banco", "doctor": "diagnóstico", "dashboard": "painel"}
SITE_NAME = r"(?P<name>[A-Za-z0-9][A-Za-z0-9._-]{0,99})"


def suggest_domain(path_or_name: str) -> str:
    """Domínio a partir do nome da pasta: minúsculas, sem www. nem .test, o resto vira hífen."""
    name = Path(path_or_name).name.lower()
    if name.startswith("www."):
        name = name[4:]
    if name.endswith(".test"):
        name = name[:-5]
    name = re.sub(r"[^a-z0-9-]+", "-", name)
    return name.strip("-")


def validate_domain(domain: str) -> Tuple[bool, str]:
    """(válido, sugestão). O domínio é só o nome, sem o .test, que o backend acrescenta."""
    ok = bool(domain) and bool(DOMAIN.match(domain)) and not domain.startswith("-")
    return ok, domain if ok else suggest_domain(domain)


def _result(result) -> Dict[str, Any]:
    lines = (result.output or "").strip().splitlines()
    return {"ok": result.ok, "code": result.code, "output": "\n".join(lines[-60:])}


def _folder(raw: Any) -> Path:
    text = str(raw or "")
    if not text or not os.path.isabs(os.path.expanduser(text)):
        raise HttpError(400, "informe o caminho completo da pasta")
    path = Path(os.path.abspath(os.path.expanduser(text)))  # sem resolve: o backend registra o caminho escolhido
    if not path.is_dir():
        raise HttpError(400, "pasta não existe")
    return path


def register_sites_api(app) -> None:
    srv = app.server

    def backend():
        if not app.backend.available:
            raise HttpError(409, "Sem Lerd ou Valet: instale um dos dois para gerenciar sites.")
        return app.backend

    @srv.route("GET", "/api/sites/suggest")
    def suggest(req: Request):
        return {"domain": suggest_domain(req.arg("path") or "")}

    @srv.route("POST", "/api/sites")
    def add(req: Request):
        body = req.json()
        kind = body.get("kind")
        if kind not in KINDS:
            raise HttpError(400, "kind deve ser link ou park")
        path = _folder(body.get("path"))
        if kind == "link":
            ok, suggestion = validate_domain(str(body.get("domain") or ""))
            if not ok:
                raise HttpError(400, "domínio só com letras minúsculas, números e hífen, sem .test",
                                {"suggestion": suggestion})
            result = backend().link(str(path), str(body["domain"]))
        else:
            result = backend().park(str(path))
        return _result(result)

    def site_or_404(name: str):
        site = app.site(name)
        if site is None:
            raise HttpError(404, "site não encontrado")
        return site

    @srv.route("GET", rf"/api/sites/{SITE_NAME}/versions")
    def versions(req: Request):
        """Opções do cabeçalho do site e o que o backend escreve no projeto em cada ação."""
        site = site_or_404(req.params["name"])
        return {"php": app.backend.php_versions(), "current": {"php": site.php, "node": site.node,
                                                               "secured": site.secured},
                "writes": dict(app.backend.project_writes)}

    @srv.route("PATCH", rf"/api/sites/{SITE_NAME}")
    def change(req: Request):
        site = site_or_404(req.params["name"])
        body = req.json()
        b = backend()
        try:
            if "secured" in body:
                if not isinstance(body["secured"], bool):
                    raise HttpError(400, "secured deve ser true ou false")
                return _result(b.secure(site.name) if body["secured"] else b.unsecure(site.name))
            if "php" in body:
                php = str(body["php"] or "")
                if php not in {v["version"] for v in b.php_versions()}:
                    raise HttpError(400, "versão de PHP indisponível neste backend")
                argv, cwd = b.site_argv("isolate", site.path, php, site.name)
                title = f"{site.name} · PHP {php}"
            elif "node" in body:
                node = str(body["node"] or "")
                if not NODE.match(node):
                    raise HttpError(400, "versão de Node como 22, 20.11 ou lts")
                argv, cwd = b.site_argv("isolate_node", site.path, node)
                title = f"{site.name} · Node {node}"
            else:
                raise HttpError(400, "envie secured, php ou node")
        except ValueError as err:
            raise HttpError(400, str(err)) from None
        except NotImplementedError as err:
            raise HttpError(409, str(err)) from None
        # pode construir a imagem da versão: roda numa aba do site, com a saída à vista
        session = app.spawn_terminal(cwd or site.path, title, None, site=site.name, command=shlex.join(argv))
        return 201, session.info()

    @srv.route("POST", rf"/api/sites/{SITE_NAME}/actions/(?P<action>[a-z]+)")
    def action(req: Request):
        """Ações rápidas do site: banco e diagnóstico numa aba do site; painel do Lerd no site."""
        site = site_or_404(req.params["name"])
        name = req.params["action"]
        if name not in SITE_ACTIONS:
            raise HttpError(404, "ação desconhecida")
        b = backend()
        if name == "dashboard":
            if not hasattr(b, "dashboard_url"):
                raise HttpError(409, "este backend não tem painel")
            url = b.dashboard_url(site.domain)
            result = app.runner.run(open_argv("url", url, app.env), timeout=15)
            if not result.ok:
                raise HttpError(500, (result.output or "falha ao abrir").strip())
            return {"ok": True, "url": url}
        try:
            argv, cwd = b.site_argv(name, site.path)
        except NotImplementedError:
            raise HttpError(409, f"{b.label} não tem esta ação") from None
        session = app.spawn_terminal(cwd or site.path, f"{site.name} · {SITE_ACTIONS[name]}", None, site=site.name,
                                     command=shlex.join(argv))
        return 201, session.info()

    @srv.route("PUT", rf"/api/sites/{SITE_NAME}/favorite")
    def favorite(req: Request):
        """Estrela do site: só o nome vai para favorites.json."""
        site = site_or_404(req.params["name"])
        value = req.json().get("favorite")
        if not isinstance(value, bool):
            raise HttpError(400, "favorite deve ser true ou false")
        names = [n for n in app.favorites() if n != site.name] + ([site.name] if value else [])
        app.store.save("favorites", names)
        return {"favorites": names}

    @srv.route("POST", rf"/api/sites/{SITE_NAME}/share")
    def share(req: Request):
        """Túnel público numa aba do site; fechar a aba encerra o túnel."""
        site = site_or_404(req.params["name"])
        tool = req.json().get("tool") or None
        b = backend()
        try:
            argv = b.share_argv(site.name, tool)
        except ValueError as err:
            raise HttpError(400, str(err)) from None
        except NotImplementedError as err:
            raise HttpError(409, str(err)) from None
        session = app.spawn_terminal(site.path, f"{site.name} · compartilhar", None, site=site.name,
                                     command=shlex.join(argv))
        return 201, session.info()

    @srv.route("GET", r"/api/terminals/(?P<tid>[0-9a-f]+)/public-url")
    def public_url(req: Request):
        session = app.terminals.get(req.params["tid"])
        if session is None:
            raise HttpError(404, "terminal não encontrado")
        return {"url": extract_public_url(session.history().decode("utf-8", "replace"))}

    # ── remover ─────────────────────────────────────────────
    released: Dict[str, str] = {}  # sites tirados da lista ou do backend nesta execução: só eles vão para a Lixeira

    @srv.route("POST", rf"/api/sites/{SITE_NAME}/remove")
    def remove(req: Request):
        site = site_or_404(req.params["name"])
        level = req.json().get("level")
        if level == "list":
            if site.kind != "manual":
                raise HttpError(409, "só site manual sai da lista; este está registrado no backend")
            manual = {k: v for k, v in app.manual_sites().items() if k != site.name}
            app.store.save("sites", manual)
            released[site.name] = site.path
            return {"ok": True}
        if level == "backend":
            if site.kind == "manual":
                raise HttpError(409, "site manual não está no backend: use remover da lista")
            b = backend()
            if site.kind == "parked":  # Valet: o equivalente é esquecer a pasta mãe inteira
                if not req.json().get("parent"):
                    raise HttpError(409, "site parkeado: desregistrar esquece a pasta mãe inteira, com todos os sites dela",
                                    {"needs_parent": str(Path(site.path).parent)})
                result = b.unpark(str(Path(site.path).parent))
            else:
                result = b.unlink(site.name)
            if result.ok:
                released[site.name] = site.path
            return _result(result)
        raise HttpError(400, "level deve ser list ou backend")

    @srv.route("POST", "/api/sites/trash")
    def trash(req: Request):
        """Pasta do site para a Lixeira: só de site já desregistrado pelo app, com o nome digitado; nunca apaga."""
        body = req.json()
        name = str(body.get("name") or "")
        path = released.get(name)
        if not path:
            raise HttpError(409, "primeiro tire o site da lista ou desregistre do backend")
        if any(s.path == path for s in app.sites()):
            raise HttpError(409, "o backend ainda lista um site nesta pasta")
        if body.get("confirm") != name:
            raise HttpError(400, "digite o nome do site exatamente para confirmar")
        folder = Path(path)
        if not folder.is_dir() or folder == Path(app.env.get("HOME") or Path.home()) or len(folder.parts) < 3:
            raise HttpError(400, "esta pasta não pode ir para a Lixeira por aqui")
        moved = move_to_trash(folder, app.data_dir, app.runner)
        released.pop(name, None)
        return {"ok": True, "moved_to": str(moved)}

    # ── PHP e Node da aba ────────────────────────────────────
    runtime_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    @srv.route("GET", rf"/api/sites/{SITE_NAME}/runtime")
    def runtime(req: Request):
        site = site_or_404(req.params["name"])
        hit = runtime_cache.get(site.name)
        if hit and time.monotonic() - hit[0] < RUNTIME_TTL:
            return hit[1]
        env = terminal_env(app.terminals.base_env)
        home = env.get("HOME") or str(Path.home())
        info: Dict[str, Any] = {"php": site.php, "node": site.node}
        b = app.backend
        if b.available and b.name == "lerd" and site.path and Path(site.path).is_dir():
            info.update(parse_which(b.runner.run(b.argv("which"), cwd=site.path, timeout=10).output))
            info["shim"] = shim_status(env.get("PATH", ""), home)
        elif b.available:
            info["php"] = parse_php_version(b.runner.run(["php", "-v"], cwd=site.path or None, timeout=10).output)
        runtime_cache[site.name] = (time.monotonic(), info)
        return info

    # ── comandos do projeto ──────────────────────────────────
    def custom_commands(name: str) -> list:
        data = app.store.load("quick", {})
        items = data.get(name) if isinstance(data, dict) else None
        return items if isinstance(items, list) else []

    def save_custom(name: str, items: list) -> None:
        data = app.store.load("quick", {})
        data = data if isinstance(data, dict) else {}
        data[name] = items
        app.store.save("quick", data)

    def command_list(site) -> Dict[str, Any]:
        lerd = app.backend.available and app.backend.name == "lerd"
        return {"commands": project_commands(site.path, lerd=lerd, custom=custom_commands(site.name))}

    @srv.route("GET", rf"/api/sites/{SITE_NAME}/commands")
    def commands(req: Request):
        return command_list(site_or_404(req.params["name"]))

    @srv.route("POST", rf"/api/sites/{SITE_NAME}/commands")
    def add_command(req: Request):
        site = site_or_404(req.params["name"])
        body = req.json()
        command = str(body.get("command") or "").strip()
        label = str(body.get("label") or command).strip()[:60]
        if not command or len(command) > 500 or "\n" in command:
            raise HttpError(400, "comando de uma linha, até 500 caracteres")
        items = [c for c in custom_commands(site.name) if c.get("command") != command]
        save_custom(site.name, items + [{"label": label, "command": command}])
        return 201, command_list(site)

    @srv.route("DELETE", rf"/api/sites/{SITE_NAME}/commands")
    def remove_command(req: Request):
        site = site_or_404(req.params["name"])
        command = req.arg("command") or ""
        save_custom(site.name, [c for c in custom_commands(site.name) if c.get("command") != command])
        return command_list(site)

    @srv.route("GET", rf"/api/sites/{SITE_NAME}/recent")
    def recent(req: Request):
        """Últimos comandos do site, das sessões de terminal registradas."""
        site = site_or_404(req.params["name"])
        return {"commands": recent_commands(app.hub.sessions.list(site.name), site.name, 20)}

    register_site_harness_api(srv, site_or_404, SITE_NAME)

    # ── logs ─────────────────────────────────────────────────
    @srv.route("GET", rf"/api/sites/{SITE_NAME}/log")
    def site_log(req: Request):
        """storage/logs/laravel.log em pedaços: sem offset, o fim do arquivo; com offset, o que chegou depois."""
        site = site_or_404(req.params["name"])
        raw = req.arg("offset")
        offset = int(raw) if raw and raw.isdigit() else None
        path = Path(site.path) / "storage" / "logs" / "laravel.log"
        return {"path": str(path), "folder": str(path.parent), **read_log(path, offset)}

    @srv.route("POST", rf"/api/sites/{SITE_NAME}/lerd-logs/(?P<target>[a-z0-9][a-z0-9._-]{{0,40}})")
    def lerd_logs(req: Request):
        """Logs do Lerd numa aba do site: php (PHP-FPM do projeto), nginx ou um serviço instalado."""
        site = site_or_404(req.params["name"])
        b = backend()
        if b.name != "lerd":
            raise HttpError(409, f"{b.label} não tem lerd logs")
        target = req.params["target"]
        services = {str(s.get("name")) for s in (b.api_get("/api/services") or []) if isinstance(s, dict)}
        if target == "php":
            args = ["logs", "-f"]
        elif target == "nginx" or target in services:
            args = ["logs", target, "-f"]
        else:
            raise HttpError(404, "log desconhecido")
        session = app.spawn_terminal(site.path, f"{site.name} · logs {target}", None, site=site.name,
                                     command=shlex.join(b.argv(*args)))
        return 201, session.info()

