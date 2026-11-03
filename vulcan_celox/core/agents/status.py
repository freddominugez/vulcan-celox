"""Diagnóstico das fontes de agentes para o --doctor e para a tela de histórico. Só lê; nunca cria o índice."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from vulcan_celox.core.agents import discovery, history
from vulcan_celox.core.agents.index import index_path

CLAUDE_DEFAULT_CLEANUP_DAYS = 30


def claude_cleanup_days(root: Path) -> Dict[str, Any]:
    """cleanupPeriodDays do settings.json do Claude Code (padrão 30 quando ausente). Só leitura."""
    value: Optional[int] = None
    try:
        data = json.loads((root / "settings.json").read_text(encoding="utf-8"))
        raw = data.get("cleanupPeriodDays") if isinstance(data, dict) else None
        value = int(raw) if isinstance(raw, (int, float)) else None
    except (OSError, ValueError):
        value = None
    return {"days": value if value is not None else CLAUDE_DEFAULT_CLEANUP_DAYS, "configured": value is not None}


def indexed_counts(data_dir: Path) -> Dict[str, int]:
    path = index_path(data_dir)
    if not path.is_file():
        return {}
    try:
        db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)  # as_uri escapa ? e # no caminho
        try:
            counts = dict(db.execute("SELECT agent, COUNT(*) FROM sessions GROUP BY agent").fetchall())
            counts["events"] = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        finally:
            db.close()
        return counts
    except sqlite3.DatabaseError:
        return {"erro": 1}


def last_error(data_dir: Path) -> Optional[str]:
    """Último erro do observador de agentes, gravado no índice pelo app."""
    path = index_path(data_dir)
    if not path.is_file():
        return None
    try:
        db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        try:
            row = db.execute("SELECT value FROM meta WHERE key = 'last_error'").fetchone()
        finally:
            db.close()
    except sqlite3.DatabaseError:
        return None
    if not row:
        return None
    try:
        data = json.loads(row[0])
        return f"{data.get('at')}: {data.get('message')}"
    except (TypeError, ValueError, AttributeError):
        return row[0]


def collect(env: Optional[Mapping[str, str]] = None, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    env = os.environ if env is None else env
    claude = discovery.claude_root(env)
    codex_roots = discovery.codex_roots(env)
    zstd = discovery.zstd_bin(env)
    codex_files, zst = discovery.codex_session_files(codex_roots, zstd)
    out = {
        "claude_dir": str(claude), "claude_found": claude.is_dir(),
        "codex_dirs": [str(p) for p in codex_roots], "codex_found": any(p.is_dir() for p in codex_roots),
        "claude_session_files": len(discovery.claude_session_files(claude)),
        "codex_session_files": len(codex_files), "codex_zst_ignored": zst,
        "codex_zst_reader": zstd,  # Com o comando, os.jsonl.zst são lidos; sem ele, ignorados e contados
        "claude_cleanup": claude_cleanup_days(claude),
        "fts5": history.fts5_available(),
    }
    if data_dir is not None:
        out["indexed"] = indexed_counts(Path(data_dir))
        out["last_error"] = last_error(Path(data_dir))
        out["index_path"] = str(index_path(data_dir))
    return out
