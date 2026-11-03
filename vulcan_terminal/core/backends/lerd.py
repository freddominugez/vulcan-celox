"""Backend Lerd (github.com/lerd-env/lerd, MIT): CLI `lerd` e API local do painel."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from vulcan_terminal.core import miniyaml
from vulcan_terminal.core.backends.base import Backend, EnvStatus
from vulcan_terminal.core.runner import Result
from vulcan_terminal.core.sites import KIND_ORDER, Site, discover_sites

SERVICE_TIMEOUT = 300.0  # um start pode baixar imagens e subir a VM do Podman
DEFAULT_API = "http://127.0.0.1:7073"
API_TIMEOUT = 1.5
SITE_TERMINAL_ACTIONS = {"db": "db:shell", "doctor": "site:doctor"}
SHARE_TOOLS = ("cloudflare", "expose", "ngrok", "localhost-run", "serveo", "pinggy")  # lerd share --help
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # API é loopback: ignora proxy do ambiente


class LerdBackend(Backend):
    name = "lerd"
    label = "Lerd"
    available = True
    project_writes = {"link": ".php-version", "php": ".php-version (e .lerd.yaml, se existir)",
                      "node": "a versão de Node do projeto", "secure": "APP_URL no .env"}  # docs do Lerd

    def __init__(self, bin_path=None, runner=None, valet_home=None, data_dir=None, api_base: str = DEFAULT_API):
        super().__init__(bin_path, runner=runner, valet_home=None)
        self.data_dir = data_dir
        self.api_base = api_base.rstrip("/")
        self._version: Optional[str] = None

    def argv(self, *args: str) -> List[str]:
        return [str(self.bin_path), *args]

    # ── serviços ─────────────────────────────────────────────────────────
    def start(self) -> Result:
        return self.runner.run(self.argv("start"), timeout=SERVICE_TIMEOUT)

    def stop(self) -> Result:
        return self.runner.run(self.argv("stop"), timeout=SERVICE_TIMEOUT)

    def restart(self) -> Result:
        stopped = self.stop()
        if not stopped.ok:
            return stopped
        started = self.start()
        return Result(started.code, stopped.stdout + started.stdout, stopped.stderr + started.stderr,
                      stopped.duration + started.duration, started.timed_out)

    def version(self) -> str:
        r = self.runner.run(self.argv("--version"), timeout=10)
        match = re.search(r"(\d+\.\d+\.\d+[\w.-]*)", r.stdout or "")
        return match.group(1) if (r.ok and match) else ""

    def dashboard_url(self, domain: str = "") -> str:
        """Painel do Lerd; com domínio, abre direto no site (rota #sites/<domínio> do próprio painel)."""
        return self.api_base + "/" + (f"#sites/{domain}" if domain else "")

    def status(self) -> EnvStatus:
        if self._version is None:
            self._version = self.version()
        data = self.api_get("/api/status")
        if not isinstance(data, dict):
            return EnvStatus(False, f"{self._label()} parado (painel indisponível)")
        return summarize_status(data, self._label())

    def _label(self) -> str:
        return f"{self.label} {self._version}".strip()

    # ── API local do painel ──────────────────────────────────────────────
    def api_get(self, path: str, timeout: float = API_TIMEOUT) -> Any:
        """GET JSON na API do Lerd; None se o painel não responder."""
        try:
            with _NO_PROXY.open(self.api_base + path, timeout=timeout) as resp:  # noqa: S310 (só loopback)
                return json.loads(resp.read().decode("utf-8"))
        except (OSError, ValueError):
            return None

    # ── ações de site ─────────────────────────────────────────
    # link, isolate e isolate:node agem na pasta atual (lerd --help); os demais recebem o nome ou a pasta
    def site_command(self, action: str, *args: str) -> Tuple[List[str], Optional[str]]:
        if action == "link":
            path, domain = args
            return self.argv("link", *([domain] if domain else [])), path
        if action == "isolate":
            path, php, _name = args
            return self.argv("isolate", php), path
        if action == "isolate_node":
            path, node = args
            return self.argv("isolate:node", node), path
        if action in ("unlink", "park", "unpark", "secure", "unsecure"):
            return self.argv(action, args[0]), None
        if action in SITE_TERMINAL_ACTIONS:  # Interativos ou longos, rodam numa aba do site
            return self.argv(SITE_TERMINAL_ACTIONS[action]), args[0]
        return super().site_command(action, *args)

    def share_argv(self, name: str, tool: Optional[str] = None) -> List[str]:
        if tool and tool not in SHARE_TOOLS:
            raise ValueError(f"ferramenta de compartilhamento desconhecida: {tool}")
        return self.argv("share", name, *([f"--{tool}"] if tool else []))

    def php_versions(self) -> List[Dict[str, Any]]:
        try:
            data = self.api_get("/api/status")
        except OSError:
            data = None
        fpms = data.get("php_fpms") if isinstance(data, dict) else None
        default = str(data.get("php_default") or "") if isinstance(data, dict) else ""
        out = {}
        for row in fpms if isinstance(fpms, list) else []:
            if isinstance(row, dict) and row.get("version"):
                version = str(row["version"])
                out[version] = {"version": version, "running": bool(row.get("running")),
                                "patch": str(row.get("patch") or ""), "default": version == default}
        return [out[v] for v in sorted(out, key=_version_key)]

    def api_post(self, path: str, body: Optional[dict] = None, timeout: float = 10.0) -> int:
        """POST na API do Lerd com o cabeçalho que o painel dele manda (X-Lerd-CSRF); devolve o código HTTP."""
        data = json.dumps(body or {}).encode("utf-8")
        request = urllib.request.Request(self.api_base + path, data=data, method="POST",
                                         headers={"Content-Type": "application/json", "X-Lerd-CSRF": "1"})
        try:
            with _NO_PROXY.open(request, timeout=timeout) as resp:  # noqa: S310 (só loopback)
                return resp.status
        except urllib.error.HTTPError as err:
            return err.code
        except OSError:
            return 0

    # ── sites ────────────────────────────────────────────────────────────
    def registry_rows(self) -> List[dict]:
        """Sites registrados: API do painel, ou sites.yaml quando o painel está fora."""
        rows = self.api_get("/api/sites")
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
        if self.data_dir is None:
            return []
        try:
            data = miniyaml.loads(Path(self.data_dir, "sites.yaml").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, miniyaml.MiniYamlError):
            return []
        sites = data.get("sites") if isinstance(data, dict) else None
        return [s for s in sites if isinstance(s, dict)] if isinstance(sites, list) else []

    def list_sites(self, manual: Optional[Mapping[str, str]] = None) -> List[Site]:
        found = {}
        for row in self.registry_rows():
            site = site_from_row(row)
            if site is not None and site.domain not in found:
                found[site.domain] = site
        for site in discover_sites(None, manual):
            found.setdefault(site.domain, site)
        return sorted(found.values(), key=lambda s: (KIND_ORDER.index(s.kind), s.name.lower()))


def _version_key(version: str):
    return [int(x) if x.isdigit() else 0 for x in version.split(".")]


def summarize_status(data: Mapping[str, Any], label: str = "Lerd") -> EnvStatus:
    """Resumo de uma linha a partir de GET /api/status."""
    nginx = bool((data.get("nginx") or {}).get("running"))
    dns = data.get("dns") or {}
    fpms = [f for f in (data.get("php_fpms") or []) if isinstance(f, dict)]
    running_fpms = [str(f.get("version")) for f in fpms if f.get("running")]
    parts = [label, "nginx ok" if nginx else "nginx parado"]
    if dns.get("enabled"):
        parts.append(f"DNS .{dns.get('tld') or 'test'} {'ok' if dns.get('ok') else 'com problema'}")
    else:
        parts.append("DNS .localhost")
    if data.get("php_default"):
        parts.append(f"PHP {data['php_default']}")
    if not data.get("watcher_running", True):
        parts.append("watcher parado")
    details = {"nginx": nginx, "dns_ok": bool(dns.get("ok")), "tld": dns.get("tld"),
               "php_default": data.get("php_default"), "php_running": running_fpms,
               "watcher": bool(data.get("watcher_running"))}
    return EnvStatus(nginx, " · ".join(parts), details)


def site_from_row(row: Mapping[str, Any]) -> Optional[Site]:
    """Converte um registro da API (/api/sites) ou do sites.yaml em Site."""
    domains = row.get("domains") or ([row["domain"]] if row.get("domain") else [])
    domains = [d for d in domains if isinstance(d, str) and d]
    name = str(row.get("name") or "")
    if not domains or not name:
        return None
    domain = domains[0]
    secured = bool(row.get("tls") if "tls" in row else row.get("secured"))
    return Site(name=name, domain=domain, path=str(row.get("path") or ""), kind="lerd",
                tld=domain.rsplit(".", 1)[-1], secured=secured,
                php=str(row.get("php_version") or ""), node=str(row.get("node_version") or ""))
