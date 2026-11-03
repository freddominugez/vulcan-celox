"""Quais pastas o app pode tratar como projeto: nunca as de dados dos agentes, nem uma pasta que as contenha."""

from __future__ import annotations

from pathlib import Path
from typing import List, Mapping, Optional

from vulcan_terminal.core.agents import discovery


def touches_agent_data(root: str, env: Optional[Mapping[str, str]] = None) -> bool:
    """Verdadeiro se a pasta está dentro de uma pasta de dados de agente ou contém uma (a pasta pessoal, por exemplo)."""
    try:
        real = Path(root).resolve()
    except (OSError, ValueError):
        return True
    home = Path(env["HOME"]) if env and env.get("HOME") else Path.home()
    for data in [discovery.claude_root(env), *discovery.codex_roots(env), home / ".gemini", home / ".cursor"]:
        try:
            data = data.resolve()
        except OSError:
            continue
        if real == data or real.is_relative_to(data) or data.is_relative_to(real):
            return True
    return False


def known_folders(app) -> List[str]:
    """Pastas de site, de projeto Node salvo e de sessão indexada, sem as que tocam os dados dos agentes."""
    known = [s.path for s in app.sites() if s.path]
    node = getattr(app, "node", None)
    if node is not None:
        known += list(node.saved().values())
    for s in app.agents.index.sessions():
        known += [s.project_root, s.cwd]
    return [path for path in dict.fromkeys(known) if path and not touches_agent_data(path, app.env)]


def known_root(app, root: str) -> bool:
    """Só pasta de site, de projeto Node salvo ou de sessão indexada."""
    if touches_agent_data(root, app.env):
        return False
    real = Path(root).resolve()
    for path in known_folders(app):
        try:
            if Path(path).resolve() == real:
                return True
        except OSError:
            continue
    return False
