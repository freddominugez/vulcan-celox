"""Estado do ambiente do Lerd para a tela Ambiente: componentes de /api/status e serviços de /api/services."""

from __future__ import annotations

import re
from typing import Any, Dict, List

SERVICE_ACTIONS = ("start", "stop", "restart")
# versões com imagem publicada pelo Lerd (docs/usage/php-versions.md: 7.4 e 8.0 a 8.6; 8.6 é prévia)
SUPPORTED_PHP = ("7.4", "8.0", "8.1", "8.2", "8.3", "8.4", "8.5")
_PHP_LINE = re.compile(r"^\s*(\*)?\s*(\d+\.\d+)\b")


def lerd_components(status: Any) -> List[Dict[str, Any]]:
    """DNS, nginx, cada PHP-FPM e o watcher, com ok e um rótulo curto."""
    if not isinstance(status, dict):
        return []
    out: List[Dict[str, Any]] = []
    dns = status.get("dns") if isinstance(status.get("dns"), dict) else {}
    out.append({"id": "dns", "label": f"DNS .{dns.get('tld') or 'test'}", "ok": bool(dns.get("ok"))})
    nginx = status.get("nginx") if isinstance(status.get("nginx"), dict) else {}
    out.append({"id": "nginx", "label": "nginx", "ok": bool(nginx.get("running"))})
    for fpm in status.get("php_fpms") or []:
        if isinstance(fpm, dict) and fpm.get("version"):
            version = str(fpm["version"])
            out.append({"id": f"php-{version}", "label": f"PHP-FPM {fpm.get('patch') or version}",
                        "ok": bool(fpm.get("running")), "xdebug": bool(fpm.get("xdebug_enabled")),
                        "default": version == str(status.get("php_default") or "")})
    out.append({"id": "watcher", "label": "watcher", "ok": bool(status.get("watcher_running"))})
    return out


def lerd_services(rows: Any) -> List[Dict[str, Any]]:
    """Serviços instalados (mysql, postgres, redis, mailpit...) no formato que o painel do Lerd lê."""
    out = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        out.append({"name": str(row["name"]), "active": row.get("status") == "active",
                    "status": str(row.get("status") or ""), "version": str(row.get("version") or ""),
                    "pinned": bool(row.get("pinned")), "connection_url": str(row.get("connection_url") or ""),
                    "sites": int(row.get("site_count") or 0) if str(row.get("site_count") or "0").isdigit() else 0})
    return out


def parse_php_list(text: str) -> List[Dict[str, Any]]:
    """Saída de `lerd php:list`: uma versão por linha, a padrão marcada com *."""
    out = []
    for line in (text or "").splitlines():
        match = _PHP_LINE.match(line)
        if match:
            out.append({"version": match.group(2), "default": bool(match.group(1))})
    return out


def parse_php_m(text: str) -> Dict[str, List[str]]:
    """`php -m`: módulos PHP e módulos Zend, sem os cabeçalhos."""
    out: Dict[str, List[str]] = {"php": [], "zend": []}
    section = "php"
    for line in (text or "").splitlines():
        name = line.strip()
        if not name:
            continue
        if name.startswith("["):
            section = "zend" if "Zend" in name else "php"
            continue
        out[section].append(name)
    return out


def parse_ext_list(text: str) -> Dict[str, Any]:
    """`lerd php:ext list`: extensões declaradas e, por versão, o que carregou ou o aviso do Lerd."""
    declared: List[str] = []
    per_version: Dict[str, str] = {}
    mode = None
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("Declared"):
            mode = "declared"
        elif stripped.startswith("Per version"):
            mode = "versions"
        elif mode == "declared" and stripped.startswith("- "):
            declared.append(stripped[2:].strip())
        elif mode == "versions":
            match = re.match(r"^PHP\s+(\d+\.\d+)\s+(.*)$", stripped)
            if match:
                per_version[match.group(1)] = match.group(2).strip()
    return {"declared": declared, "per_version": per_version}


# ── Xdebug por versão ─────────────────────────────────────────
XDEBUG_MODES = ("debug", "coverage", "develop", "profile", "trace", "gcstats")  # os que `lerd xdebug on --mode` aceita
XDEBUG_PORT = 9003


def xdebug_mode_ok(mode: str) -> bool:
    parts = str(mode or "").split(",")
    return 0 < len(mode or "") <= 60 and all(p in XDEBUG_MODES for p in parts)


def parse_xdebug_status(text: str) -> Dict[str, Dict[str, Any]]:
    """`lerd xdebug status`: tabela Version, Xdebug (enabled/disabled), Mode; sob demanda aparece junto do modo."""
    out: Dict[str, Dict[str, Any]] = {}
    for line in (text or "").splitlines():
        cols = line.split()
        if len(cols) < 2 or not re.match(r"^\d+\.\d+$", cols[0]):
            continue
        rest = cols[2:]
        on_demand = any("demand" in c.lower() or "trigger" in c.lower() for c in rest)
        mode = next((c for c in rest if "demand" not in c.lower() and "trigger" not in c.lower()), "")
        out[cols[0]] = {"enabled": cols[1].lower() in ("enabled", "on"), "mode": mode, "on_demand": on_demand}
    return out


def xdebug_argv(version: str, enabled: bool, mode: str = "debug", on_demand: bool = False) -> List[str]:
    if not enabled:
        return ["xdebug", "off", version]
    return ["xdebug", "on", version, "--mode", mode] + (["--on-demand"] if on_demand else [])

