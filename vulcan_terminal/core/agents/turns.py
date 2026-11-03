"""A sessão agrupada por pedido: o que o agente fez em cada um. Vem dos eventos e das edições já indexados."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from vulcan_terminal.core.agents import edits as edit_log

ASK_MAX = 400
COMMANDS_MAX = 30
EVENTS_PAGE = 1000
FILE_MARKS = {"read": 0, "edit": 1, "new": 2, "delete": 3}


def _empty(number: int, at: str, ask: str) -> Dict[str, Any]:
    return {"turn": number, "at": at, "ask": ask, "files": {}, "commands": [], "commands_total": 0, "edits": 0}


def group(events, rows: List[Dict]) -> List[Dict[str, Any]]:
    """Mesma contagem do leitor: cada evento de usuário abre um turno. O que vem antes do primeiro pedido é o turno 0."""
    turns: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for event in events:
        if event.kind == "user":
            number = (current["turn"] if current else 0) + 1
            current = _empty(number, event.at, (event.text or "")[:ASK_MAX])
            turns.append(current)
            continue
        if event.kind not in ("file", "command"):
            continue
        if current is None:
            current = _empty(0, event.at, "")
            turns.append(current)
        if event.kind == "file":
            known = current["files"].get(event.text)
            if known is None or FILE_MARKS.get(event.tool, 0) > FILE_MARKS.get(known["kind"], 0):
                current["files"][event.text] = {"path": event.text, "kind": event.tool, "seq": None}
        else:
            current["commands_total"] += 1
            if len(current["commands"]) < COMMANDS_MAX:
                current["commands"].append({"text": event.text, "kind": event.tool or "shell", "at": event.at})
    by_number = {t["turn"]: t for t in turns}
    for row in rows:
        turn = by_number.get(row["turn"] or 0)
        if turn is None:
            continue
        turn["edits"] += 1
        entry = turn["files"].setdefault(row["path"], {"path": row["path"], "kind": "edit", "seq": None})
        if row["state"] != "failed":
            entry["seq"] = row["seq"]
    for turn in turns:
        turn["files"] = list(turn["files"].values())
    return turns


def turns_of(index, session_id: str, start: int = 0, limit: int = 50) -> Dict[str, Any]:
    events = []
    position: Optional[int] = 0
    while position is not None:
        page, position = index.events(session_id, position, EVENTS_PAGE)
        events.extend(page)
    all_turns = group(events, edit_log.rows_of(index, session_id, 0, 100000))
    end = start + limit
    return {"turns": all_turns[start:end], "total": len(all_turns), "next": end if end < len(all_turns) else None}
