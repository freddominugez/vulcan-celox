"""Histórico unificado dos dois agentes: busca por conteúdo em pedidos, respostas, comandos e arquivos.

Tabela FTS5 `history` com conteúdo externo na tabela `events`, mantida por gatilhos, ignorando acentos.
Sem FTS5 no SQLite, a busca cai para LIKE (sem ignorar acentos) e o --doctor avisa.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Dict, List, Optional

KINDS = {"pedidos": "user", "respostas": "assistant", "comandos": "command", "arquivos": "file"}
MARK_OPEN, MARK_CLOSE = "\x02", "\x03"
_WORDS = re.compile(r"\w+", re.UNICODE)
FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS history USING fts5(
  text, content='events', content_rowid='id', tokenize='unicode61 remove_diacritics 2');
CREATE TRIGGER IF NOT EXISTS events_history_ai AFTER INSERT ON events BEGIN
  INSERT INTO history(rowid, text) VALUES (new.id, new.text); END;
CREATE TRIGGER IF NOT EXISTS events_history_ad AFTER DELETE ON events BEGIN
  INSERT INTO history(history, rowid, text) VALUES ('delete', old.id, old.text); END;
"""


def fts5_available() -> bool:
    try:
        db = sqlite3.connect(":memory:")
        db.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        db.close()
        return True
    except sqlite3.OperationalError:
        return False


def ensure(db: sqlite3.Connection) -> bool:
    """Cria a tabela de busca e os gatilhos. Devolve False se o SQLite não tiver FTS5."""
    try:
        existed = db.execute("SELECT 1 FROM sqlite_master WHERE name = 'history'").fetchone() is not None
        db.executescript(FTS)
    except sqlite3.OperationalError:
        return False
    if not existed and db.execute("SELECT 1 FROM events LIMIT 1").fetchone():
        db.execute("INSERT INTO history(history) VALUES ('rebuild')")  # índice antigo, sem a tabela de busca
    db.commit()
    return True


def fts_query(text: str) -> Optional[str]:
    words = _WORDS.findall(text or "")
    return " ".join('"{}"*'.format(w.replace('"', '""')) for w in words) or None


def _like_snippet(text: str, words: List[str], width: int = 70) -> str:
    low = text.lower()
    pos = min((low.find(w.lower()) for w in words if low.find(w.lower()) >= 0), default=0)
    start = max(0, pos - width)
    out = ("…" if start else "") + text[start:pos + width * 2] + ("…" if pos + width * 2 < len(text) else "")
    for w in words:
        out = re.sub(re.escape(w), lambda m: MARK_OPEN + m.group(0) + MARK_CLOSE, out, flags=re.I)
    return out


def search(db: sqlite3.Connection, fts: bool, q: str = "", kind: Optional[str] = None, agent: Optional[str] = None,
           project: Optional[str] = None, limit: int = 100) -> List[Dict]:
    filters, args = [], []
    if kind in KINDS:
        filters.append("e.kind = ?")
        args.append(KINDS[kind])
    if agent:
        filters.append("s.agent = ?")
        args.append(agent)
    if project:
        filters.append("s.project = ?")
        args.append(project)
    match = fts_query(q)
    words = _WORDS.findall(q or "")
    base = ("SELECT e.session_id, e.at, e.kind, e.tool, {snip} AS snip, s.agent, s.project, s.branch, s.cwd "
            "FROM {source} JOIN sessions s ON s.id = e.session_id WHERE {where} ORDER BY e.at DESC, e.id DESC LIMIT ?")
    if match and fts:
        sql = base.format(snip=f"snippet(history, 0, '{MARK_OPEN}', '{MARK_CLOSE}', '…', 16)",
                          source="history JOIN events e ON e.id = history.rowid",
                          where=" AND ".join(["history MATCH ?"] + filters))
        args = [match] + args
    else:
        for w in words:
            filters.append("e.text LIKE ? ESCAPE '\\'")
            args.append("%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
        sql = base.format(snip="e.text", source="events e", where=" AND ".join(filters) or "1")
    rows = db.execute(sql, args + [limit]).fetchall()
    hits = []
    for r in rows:
        text = r["snip"] or ""
        if not (match and fts):
            text = _like_snippet(text, words) if words else (text if len(text) <= 240 else text[:239] + "…")
        hits.append({"session_id": r["session_id"], "at": r["at"], "kind": r["kind"], "tool": r["tool"],
                     "text": text, "agent": r["agent"], "project": r["project"], "branch": r["branch"]})
    return hits
