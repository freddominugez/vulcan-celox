"""Interface-free diagnostics: detected backend, environment state and sites."""

from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Optional

from vulcan_celox import __version__
from vulcan_celox.core import lerd_quirks, paths, server_log
from vulcan_celox.core.agents import pricing, usage
from vulcan_celox.core.agents.status import collect as agents_status
from vulcan_celox.core.backends import detect_backend
from vulcan_celox.core.store import Store


def collect(env: Optional[Mapping[str, str]] = None, runner=None) -> Dict[str, Any]:
    backend = detect_backend(env, runner=runner)
    status = backend.status()
    manual = Store(paths.data_dir(env)).load("sites", {})
    sites = backend.list_sites(manual if isinstance(manual, dict) else {})
    version = backend.version() if hasattr(backend, "version") and backend.available else ""
    return {
        "app_version": __version__,
        "data_dir": str(paths.data_dir(env)),
        "backend": backend.name,
        "backend_label": backend.label,
        "backend_bin": str(backend.bin_path) if backend.bin_path else None,
        "backend_version": version,
        "dashboard": backend.dashboard_url() if hasattr(backend, "dashboard_url") else None,
        "running": status.running,
        "summary": status.summary,
        "details": status.details,
        "sites": [{"name": s.name, "domain": s.domain, "url": s.url, "kind": s.kind,
                   "php": s.php, "secured": s.secured, "path": s.path} for s in sites],
        "lerd_contornos": lerd_quirks.status(version) if backend.name == "lerd" else None,  # see lerd_quirks.py
        "agents": agents_status(env, paths.data_dir(env)),
        "precos": pricing.describe(paths.data_dir(env)),
        "uso_30_dias": usage.doctor_summary(paths.data_dir(env)),
        "logs": dict(zip(("servidor", "erro"), map(str, server_log.log_paths(paths.data_dir(env))))),
        "memory_last_error": (Store(paths.data_dir(env)).load("memoria_status", {}) or {}).get("last_error"),
    }


def render(env: Optional[Mapping[str, str]] = None, runner=None) -> str:
    return json.dumps(collect(env, runner), ensure_ascii=False, indent=2)
