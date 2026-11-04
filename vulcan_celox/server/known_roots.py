"""Which folders the app may treat as a project: never the agents' data folders, nor a folder that contains them."""

from __future__ import annotations

from pathlib import Path
from typing import List, Mapping, Optional

from vulcan_celox.core.agents import discovery


def touches_agent_data(root: str, env: Optional[Mapping[str, str]] = None) -> bool:
    """True if the folder is inside an agent data folder or contains one (the home folder, for example)."""
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
    """Site folders, saved Node project folders and indexed session folders, excluding those that touch the agents' data."""
    known = [s.path for s in app.sites() if s.path]
    node = getattr(app, "node", None)
    if node is not None:
        known += list(node.saved().values())
    for s in app.agents.index.sessions():
        known += [s.project_root, s.cwd]
    return [path for path in dict.fromkeys(known) if path and not touches_agent_data(path, app.env)]


def known_root(app, root: str) -> bool:
    """Only a site folder, saved Node project folder or indexed session folder."""
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
