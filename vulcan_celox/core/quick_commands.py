"""Comandos do projeto em um clique: o que a pasta tem, o que o Lerd oferece e os do usuário."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from vulcan_celox.core.i18n import tr

MAX_SCRIPTS = 8
ARTISAN = ("about", "route:list", "migrate:status", "test")


def _scripts(path: Path) -> List[str]:
    try:
        data = json.loads((path / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return []
    scripts = data.get("scripts") if isinstance(data, dict) else None
    return [str(k) for k in scripts][:MAX_SCRIPTS] if isinstance(scripts, dict) else []


def project_commands(folder: str, lerd: bool = False, custom: Optional[List[Dict]] = None) -> List[Dict]:
    """[{label, command, custom?}] na ordem em que aparecem; os do usuário vêm no fim."""
    path = Path(folder)
    out: List[Dict] = [{"label": "git status", "command": "git status -sb"}]
    if (path / "artisan").is_file():
        out += [{"label": f"artisan {c}", "command": f"php artisan {c}"} for c in ARTISAN]
        if lerd:
            out.append({"label": tr("banco de dados"), "command": "lerd db:shell"})
    if (path / "composer.json").is_file():
        out.append({"label": "composer install", "command": "composer install"})
    out += [{"label": f"npm run {s}", "command": f"npm run {s}"} for s in _scripts(path)]
    if lerd:
        out += [{"label": tr("logs do PHP"), "command": "lerd logs -f"}, {"label": tr("diagnóstico"), "command": "lerd site:doctor"}]
    for item in custom or []:
        if isinstance(item, dict) and item.get("command"):
            out.append({"label": str(item.get("label") or item["command"]), "command": str(item["command"]), "custom": True})
    return out


# Comandos que ficam rodando até alguém parar (servidor de desenvolvimento, fila, logs, túnel)
LONG_RUNNING = [re.compile(p) for p in (
    r"\b(npm|pnpm|yarn|bun)\s+(run\s+)?dev\b", r"\bartisan\s+serve\b", r"\bqueue:(work|listen)\b",
    r"\breverb:start\b", r"\bartisan\s+horizon\b", r"\blerd\s+logs\b.*\s(-f|--follow)\b", r"\blerd\s+share\b",
    r"\btail\s+(-\w*[fF]\w*)", r"\bvite\b(?!\s+build)", r"\bwatch\b",
)]


def is_long_running(command: Optional[str]) -> bool:
    return bool(command) and any(p.search(command) for p in LONG_RUNNING)


def recent_commands(records, site: str, limit: int = 20) -> List[Dict[str, str]]:
    """Últimos comandos digitados nas sessões do site, do mais novo ao mais velho, sem repetir seguidos."""
    rows = [(str(c.get("ts") or ""), i, str(c.get("cmd") or "").strip())
            for r in records if r.site == site for i, c in enumerate(r.commands) if isinstance(c, dict)]
    out: List[Dict[str, str]] = []
    # mesmo segundo: o digitado depois (posição maior na sessão) é o mais novo
    for at, _i, command in sorted((r for r in rows if r[2]), key=lambda r: (r[0], r[1]), reverse=True):
        if out and out[-1]["command"] == command:
            continue
        out.append({"command": command, "at": at})
        if len(out) >= limit:
            break
    return out

