"""Where the sessions live: CLAUDE_CONFIG_DIR or ~/.claude; CODEX_HOME (comma-separated list) or ~/.codex."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from vulcan_celox.core.agents.jsonl_stream import LineStream


def _home(env: Mapping[str, str]) -> Path:
    return Path(env.get("HOME") or str(Path.home())).expanduser()


def claude_root(env: Optional[Mapping[str, str]] = None) -> Path:
    env = os.environ if env is None else env
    value = env.get("CLAUDE_CONFIG_DIR")
    return Path(value).expanduser() if value else _home(env) / ".claude"


def codex_roots(env: Optional[Mapping[str, str]] = None) -> List[Path]:
    env = os.environ if env is None else env
    value = env.get("CODEX_HOME")
    if value:
        return [Path(v.strip()).expanduser() for v in value.split(",") if v.strip()]
    return [_home(env) / ".codex"]


def claude_session_files(root: Path) -> List[Path]:
    """One session per file in projects/<slug>/; agent-*.jsonl are sub-agents, not sessions."""
    projects = root / "projects"
    if not projects.is_dir():
        return []
    return sorted(p for p in projects.glob("*/*.jsonl") if p.is_file() and not p.name.startswith("agent-"))


def claude_subagent_counts(root: Path) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    projects = root / "projects"
    if not projects.is_dir():
        return counts
    for sub in projects.glob("*/*/subagents/*.jsonl"):
        sid = sub.parent.parent.name
        counts[sid] = counts.get(sid, 0) + 1
    for agent_file in projects.glob("*/agent-*.jsonl"):
        for _offset, obj in LineStream(agent_file):
            sid = obj.get("sessionId")
            if isinstance(sid, str) and sid:
                counts[sid] = counts.get(sid, 0) + 1
            break
    return counts


ZSTD_PLACES = ("/opt/homebrew/bin/zstd", "/usr/local/bin/zstd", "/usr/bin/zstd")


def zstd_bin(env: Optional[Mapping[str, str]] = None, extra: Sequence[str] = ZSTD_PLACES) -> Optional[str]:
    """The zstd command, if any. VULCAN_ZSTD_BIN wins (empty: no zstd); an app opened from Finder has a
    short PATH, so it also looks in the usual places."""
    env = os.environ if env is None else env
    if "VULCAN_ZSTD_BIN" in env:
        chosen = env["VULCAN_ZSTD_BIN"]
        return chosen if chosen and os.access(chosen, os.X_OK) else None
    found = shutil.which("zstd", path=env.get("PATH"))
    return found or next((p for p in extra if os.access(p, os.X_OK)), None)


def codex_session_files(roots: List[Path], zstd: Optional[str] = None) -> Tuple[List[Path], int]:
    """(readable rollouts, count of .jsonl.zst ignored for lack of the zstd command). With the same rollout in
    both forms, the .jsonl wins."""
    files: List[Path] = []
    compressed: List[Path] = []
    for root in roots:
        for folder in ("sessions", "archived_sessions"):
            base = root / folder
            if not base.is_dir():
                continue
            for path in base.rglob("*.jsonl*"):
                if not path.is_file():
                    continue
                if path.name.endswith(".jsonl"):
                    files.append(path)
                elif path.name.endswith(".jsonl.zst"):
                    compressed.append(path)
    plain = set(files)
    compressed = [p for p in compressed if p.with_name(p.name[:-len(".zst")]) not in plain]
    if zstd:
        return sorted(plain | set(compressed)), 0
    return sorted(plain), len(set(compressed))
