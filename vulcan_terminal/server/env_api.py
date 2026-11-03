"""Tela Ambiente: serviços, versões de PHP, php.ini, extensões, Node e logs do backend."""

from __future__ import annotations

import json
import re
import os
import shlex
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict

from vulcan_terminal.core.environment import (SERVICE_ACTIONS, SUPPORTED_PHP, XDEBUG_PORT, lerd_components,
                                               lerd_services, parse_ext_list, parse_php_list, parse_php_m,
                                               parse_xdebug_status, xdebug_argv, xdebug_mode_ok)
from vulcan_terminal.core import paths
from vulcan_terminal.core.php_ini import ENV_CHANGES, KEYS, check, parse_directives
from vulcan_terminal.server.local_http import HttpError, Request

NODE = re.compile(r"^(\d+(\.\d+){0,2}|lts)$")
SERVICE_TIMEOUT = 300.0  # um start pode baixar a imagem do serviço
CLI_CACHE_S = 60.0  # A tela Ambiente atualiza a cada 15 s; php:list e xdebug status mudam só com ação
_now = time.monotonic


def _result(result) -> Dict[str, Any]:
    lines = (result.output or "").strip().splitlines()
    return {"ok": result.ok, "code": result.code, "output": "\n".join(lines[-60:])}


def register_env_api(app) -> None:
    srv = app.server

    def lerd():
        b = app.backend
        if not b.available:
            raise HttpError(409, "Sem Lerd ou Valet: instale um dos dois.")
        if b.name != "lerd":
            raise HttpError(409, f"{b.label} não tem esta tela; use o Lerd")
        return b

    @srv.route("GET", "/api/environment")
    def environment(_req: Request):
        b = app.backend
        data: Dict[str, Any] = {"backend": b.name, "label": b.label, "available": b.available,
                                "components": [], "services": []}
        if b.available and b.name == "lerd":
            data["components"] = lerd_components(b.api_get("/api/status"))
            data["services"] = lerd_services(b.api_get("/api/services"))
            data["dashboard"] = b.dashboard_url()
        elif b.available:
            data["components"] = [{"id": "nginx", "label": "nginx", "ok": b.nginx_running()}]
        return data

    @srv.route("POST", r"/api/environment/services/(?P<name>[a-z0-9][a-z0-9._-]{0,40})/(?P<action>[a-z]+)")
    def service(req: Request):
        b = lerd()
        name, action = req.params["name"], req.params["action"]
        if action not in SERVICE_ACTIONS:
            raise HttpError(404, "ação desconhecida")
        if name not in {s["name"] for s in lerd_services(b.api_get("/api/services"))}:
            raise HttpError(404, "serviço não instalado")
        return _result(b.runner.run(b.argv("service", action, name), timeout=SERVICE_TIMEOUT))

    def in_tab(b, title: str, *args: str):
        """Comando demorado do Lerd numa aba de terminal, com a saída à vista."""
        home = app.env.get("HOME") or str(Path.home())
        session = app.spawn_terminal(home, title, None, command=shlex.join(b.argv(*args)))
        return 201, session.info()

    # saídas de leitura da CLI guardadas por CLI_CACHE_S; qualquer POST desta tela limpa tudo
    cache: Dict[tuple, Any] = {}
    cache_lock = threading.Lock()

    def cli_output(b, *args: str) -> str:
        now = _now()
        with cache_lock:
            hit = cache.get(args)
            if hit and now - hit[0] < CLI_CACHE_S:
                return hit[1]
        output = b.runner.run(b.argv(*args), timeout=20).output
        with cache_lock:
            cache[args] = (now, output)
        return output

    def forget() -> None:
        with cache_lock:
            cache.clear()

    def invalidates(handler):
        """Ação que muda versões, php.ini ou Xdebug: limpa o cache antes e depois (a validação relê a lista)."""
        def wrapped(req: Request):
            forget()
            try:
                return handler(req)
            finally:
                forget()
        return wrapped

    # ── versões de PHP ────────────────────────────────────────
    def installed_php(b):
        return parse_php_list(cli_output(b, "php:list"))

    @srv.route("GET", "/api/environment/php")
    def php_versions(_req: Request):
        b = lerd()
        installed = installed_php(b)
        have = {v["version"] for v in installed}
        return {"installed": installed, "installable": [v for v in SUPPORTED_PHP if v not in have]}

    @srv.route("POST", r"/api/environment/php/(?P<version>[0-9.]{3,4})/(?P<op>use|update|install)")
    @invalidates
    def php_action(req: Request):
        b = lerd()
        version, op = req.params["version"], req.params["op"]
        if op not in ("use", "update", "install"):
            raise HttpError(404, "ação desconhecida")
        if version not in SUPPORTED_PHP:
            raise HttpError(400, "versão de PHP que o Lerd não publica")
        have = {v["version"] for v in installed_php(b)}
        if op == "install":
            return in_tab(b, f"PHP {version} · instalar", "fetch", version)
        if version not in have:
            raise HttpError(400, "versão não instalada")
        if op == "update":
            return in_tab(b, f"PHP {version} · atualizar", "php:update", version)
        return _result(b.runner.run(b.argv("use", version), timeout=120))

    # ── Xdebug por versão ─────────────────────────────────────
    @srv.route("GET", "/api/environment/xdebug")
    def xdebug_state(_req: Request):
        b = lerd()
        cli = parse_xdebug_status(cli_output(b, "xdebug", "status"))
        status = b.api_get("/api/status")
        fpms = {str(f.get("version")): f for f in (status.get("php_fpms") or []) if isinstance(f, dict)} \
            if isinstance(status, dict) else {}
        versions = []
        for v in sorted(set(cli) | set(fpms)):
            row = dict(cli.get(v) or {"enabled": False, "mode": "", "on_demand": False})
            if v in fpms:  # /api/status manda no ligado/desligado; o modo só a CLI conta
                row["enabled"] = bool(fpms[v].get("xdebug_enabled"))
            versions.append({"version": v, **row})
        return {"versions": versions, "port": XDEBUG_PORT}

    @srv.route("POST", r"/api/environment/php/(?P<version>[0-9.]{3,4})/xdebug")
    @invalidates
    def xdebug_toggle(req: Request):
        b = lerd()
        version = req.params["version"]
        body = req.json()
        enabled, mode, on_demand = body.get("enabled"), body.get("mode") or "debug", body.get("on_demand", False)
        if not isinstance(enabled, bool) or not isinstance(on_demand, bool):
            raise HttpError(400, "enabled e on_demand devem ser true ou false")
        if enabled and not (isinstance(mode, str) and xdebug_mode_ok(mode)):
            raise HttpError(400, "modo do Xdebug inválido: use debug, coverage ou debug,coverage")
        if version not in {v["version"] for v in installed_php(b)}:
            raise HttpError(400, "versão não instalada")
        title = f"PHP {version} · Xdebug {'ligar' if enabled else 'desligar'}"
        return in_tab(b, title, *xdebug_argv(version, enabled, mode, on_demand))  # reconstrói a imagem: demora

    # ── php.ini de usuário ────────────────────────────────────
    def ini_target(version: str) -> str:
        if version != "shared" and version not in SUPPORTED_PHP:
            raise HttpError(400, "versão de PHP desconhecida")
        return version

    def ini_path(version: str) -> Path:
        """Arquivo de usuário do Lerd: o 1.37.1 usa 98-user.ini e shared/95-shared.ini (a documentação cita outros
        nomes, por isso a leitura aceita os dois); a gravação sempre recebe o caminho do próprio Lerd."""
        folder = paths.lerd_data_dir(app.env) / "php" / version
        names = ("95-shared.ini", "95-lerd-shared.ini") if version == "shared" else ("98-user.ini", "98-lerd-user.ini")
        return next((folder / n for n in names if (folder / n).is_file()), folder / names[0])

    def editor_wrapper() -> str:
        """Script que o Lerd chama como EDITOR: roda este app em modo ajudante de php.ini."""
        target = Path(app.data_dir) / "hooks" / "php-ini-editor.sh"
        root = str(Path(__file__).resolve().parent.parent.parent)
        # -I: sem a pasta atual nem PYTHONPATH em sys.path; a biblioteca entra pelo caminho absoluto
        code = (f"import sys; sys.path.insert(0, {root!r}); "
                "from vulcan_terminal.core.php_ini import main; sys.exit(main(sys.argv[1:]))")
        text = f"#!/bin/sh\nexec {shlex.quote(sys.executable)} -I -c {shlex.quote(code)} \"$@\"\n"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_text(encoding="utf-8") != text:
            target.write_text(text, encoding="utf-8")
        os.chmod(target, 0o700)  # sempre: sem o bit de execução o Lerd não consegue chamar o editor
        return str(target)

    @srv.route("GET", r"/api/environment/php/(?P<version>shared|[0-9.]{3,4})/ini")
    def ini_read(req: Request):
        lerd()
        path = ini_path(ini_target(req.params["version"]))
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        return {"path": str(path), "values": parse_directives(text), "keys": list(KEYS)}

    @srv.route("POST", r"/api/environment/php/(?P<version>shared|[0-9.]{3,4})/ini")
    @invalidates
    def ini_write(req: Request):
        b = lerd()
        version = ini_target(req.params["version"])
        values = req.json().get("values")
        if not isinstance(values, dict) or not values:
            raise HttpError(400, "envie values com ao menos uma das seis chaves")
        changes = {}
        for key, value in values.items():
            value = None if value in (None, "") else str(value)
            try:
                check(str(key), value)
            except ValueError as err:
                raise HttpError(400, str(err)) from None
            changes[str(key)] = value
        env = dict(os.environ, **{"EDITOR": editor_wrapper(), "VISUAL": editor_wrapper(), ENV_CHANGES: json.dumps(changes)})
        return _result(b.runner.run(b.argv("php:ini", version), env=env, timeout=180))

    @srv.route("POST", r"/api/environment/php/(?P<version>shared|[0-9.]{3,4})/ini/open")
    @invalidates
    def ini_open(req: Request):
        b = lerd()
        version = ini_target(req.params["version"])
        return in_tab(b, f"php.ini {version}", "php:ini", version)  # editor do usuário, numa aba

    # ── extensões, só leitura ─────────────────────────────────
    @srv.route("GET", r"/api/environment/php/(?P<version>[0-9.]{3,4})/extensions")
    def extensions(req: Request):
        b = lerd()
        version = req.params["version"]
        if version not in SUPPORTED_PHP:
            raise HttpError(400, "versão de PHP desconhecida")
        # fora de um site, o Lerd escolhe a versão pelo .php-version da pasta: uma pasta neutra por versão
        probe = Path(app.data_dir) / "php-probe" / version
        probe.mkdir(parents=True, exist_ok=True)
        (probe / ".php-version").write_text(version + "\n", encoding="utf-8")
        modules = parse_php_m(b.runner.run(b.argv("php", "-m"), cwd=str(probe), timeout=60).output)
        custom = parse_ext_list(b.runner.run(b.argv("php:ext", "list"), timeout=30).output)
        return {"version": version, "php": modules["php"], "zend": modules["zend"], "declared": custom["declared"],
                "note": custom["per_version"].get(version, ""), "dashboard": b.dashboard_url()}

    # ── Node ──────────────────────────────────────────────────
    @srv.route("GET", "/api/environment/node")
    def node(_req: Request):
        b = lerd()
        status = b.api_get("/api/status")
        status = status if isinstance(status, dict) else {}
        installed = b.api_get("/api/node-versions")  # a mesma rota que o painel do Lerd usa
        return {"default": str(status.get("node_default") or ""), "manager": str(status.get("node_manager") or ""),
                "installed": [str(v) for v in installed] if isinstance(installed, list) else []}

    @srv.route("POST", r"/api/environment/node/(?P<version>[A-Za-z0-9.]{1,12})/(?P<op>install|use|remove)")
    def node_action(req: Request):
        b = lerd()
        version, op = req.params["version"], req.params["op"]
        if not NODE.match(version):
            raise HttpError(400, "versão de Node como 22, 20.11 ou lts")
        if op == "install":
            return in_tab(b, f"Node {version} · instalar", "node:install", version)
        if op == "remove":
            if req.json().get("confirm") is not True:
                raise HttpError(400, "confirme a remoção da versão")
            return _result(b.runner.run(b.argv("node:uninstall", version), timeout=120))
        return _result(b.runner.run(b.argv("node:use", version), timeout=120))

