"""Agregação do uso por turno (agent_usage) em tokens e custo estimado por grupo.

Datas no fuso local desta máquina. O custo é estimativa no preço de API (pricing.py); assinatura cobra de
outro jeito. Linha de modelo sem preço entra nos tokens, não no custo, e marca o grupo como parcial.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from vulcan_celox.core.agents import pricing
from vulcan_celox.core.agents.model import local_day
from vulcan_celox.core.i18n import tr

GROUPS = ("day", "project", "model", "agent", "session")
TOKEN_FIELDS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h", "reasoning")
BILLED = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")  # reasoning já está em output
DEFAULT_DAYS = 30
MAX_DAYS = 400
MAX_GROUPS = 2000


def parse_day(text: Optional[str]) -> Optional[date]:
    try:
        return datetime.strptime(text, "%Y-%m-%d").date() if text else None
    except ValueError:
        return None


def period(day_from: Optional[str], day_to: Optional[str], today: Optional[date] = None) -> Tuple[date, date]:
    """Período em dias locais. Padrão: os últimos 30 dias até hoje. ValueError se inválido."""
    today = today or datetime.now().astimezone().date()
    end = parse_day(day_to) if day_to else today
    if day_to and end is None:
        raise ValueError("to deve ser AAAA-MM-DD")
    start = parse_day(day_from) if day_from else end - timedelta(days=DEFAULT_DAYS - 1)
    if day_from and start is None:
        raise ValueError("from deve ser AAAA-MM-DD")
    if start > end:
        raise ValueError("from depois de to")
    if (end - start).days >= MAX_DAYS:
        raise ValueError(f"período maior que {MAX_DAYS} dias")
    return start, end


def utc_bounds(start: date, end: date) -> Tuple[str, str]:
    """Filtro largo em UTC para o SQL (um dia de folga de cada lado); o exato é por dia local no Python."""
    lo = datetime(start.year, start.month, start.day, tzinfo=timezone.utc) - timedelta(days=1)
    hi = datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=2)
    return lo.strftime("%Y-%m-%d"), hi.strftime("%Y-%m-%d")


def total_tokens(t: Dict[str, int]) -> int:
    return sum(int(t.get(k) or 0) for k in BILLED)


def _empty() -> Dict:
    return {"tokens": {k: 0 for k in TOKEN_FIELDS}, "total_tokens": 0, "cost": 0.0, "priced": 0, "unpriced": 0,
            "turns": 0, "agents": {}}


def _add(acc: Dict, row: Dict, cost: Optional[float]) -> None:
    for k in TOKEN_FIELDS:
        acc["tokens"][k] += int(row.get(k) or 0)
    n = total_tokens(row)
    acc["total_tokens"] += n
    acc["turns"] += 1
    agent = acc["agents"].setdefault(row.get("agent") or "", {"total_tokens": 0, "cost": 0.0})
    agent["total_tokens"] += n
    if cost is None:
        acc["unpriced"] += n
    else:
        acc["cost"] += cost
        acc["priced"] += n
        agent["cost"] += cost


def _finish(acc: Dict) -> Dict:
    # custo null quando nada do grupo tem preço; parcial quando só parte tem
    acc["cost"] = round(acc["cost"], 6) if acc["priced"] or not acc["unpriced"] else None
    acc["cost_partial"] = bool(acc["unpriced"] and acc["priced"])
    for a in acc["agents"].values():
        a["cost"] = round(a["cost"], 6)
    return acc


def _key(row: Dict, group: str, day: str) -> str:
    if group == "day":
        return day
    if group == "project":
        return row.get("project") or tr("(sem projeto)")
    if group == "model":
        return pricing.normalize(row.get("model") or "") or tr("(sem modelo)")
    if group == "agent":
        return row.get("agent") or ""
    return row.get("session_id") or ""


def aggregate(rows: Iterable[Dict], table: Dict[str, Dict], group: str, start: date, end: date,
              limit: int = MAX_GROUPS) -> Dict:
    if group not in GROUPS:
        raise ValueError("group deve ser " + ", ".join(GROUPS))
    lo, hi = start.isoformat(), end.isoformat()
    groups: Dict[str, Dict] = {}
    total = _empty()
    for row in rows:
        day = local_day(row.get("at"))
        if not day or not lo <= day <= hi:
            continue
        cost = pricing.cost(row, table)
        key = _key(row, group, day)
        acc = groups.get(key)
        if acc is None:
            acc = groups[key] = _empty()
            acc["key"] = key
            if group == "session":
                acc.update(agent=row.get("agent") or "", project=row.get("project") or "", first_at=row.get("at"))
        if group == "session":
            acc["last_at"] = row.get("at")
            acc["model"] = row.get("model") or ""
        _add(acc, row, cost)
        _add(total, row, cost)
    if group == "day":
        ordered = sorted(groups.values(), key=lambda g: g["key"])
    else:
        ordered = sorted(groups.values(), key=lambda g: (-g["total_tokens"], g["key"]))
    return {"group": group, "from": lo, "to": hi, "currency": pricing.CURRENCY,
            "groups": [_finish(g) for g in ordered[:limit]], "truncated": len(ordered) > limit,
            "total": _finish(total), "estimate_note": tr(NOTE)}


NOTE = ("Estimativa no preço da API. Assinatura (Claude Max, ChatGPT) cobra de outro jeito; "
        "o valor real da sua conta pode ser bem diferente.")


def days_between(start: date, end: date) -> List[str]:
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


CSV_HEADER = ("grupo", "chave", "agente", "projeto", "turnos", "input", "output", "cache_read", "cache_write_5m",
              "cache_write_1h", "reasoning", "total_tokens", "custo_usd", "custo_parcial")


def to_csv(report: Dict) -> str:
    """CSV de um relatório: só ids, projetos, modelos e números; nenhum texto de sessão."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(CSV_HEADER)
    group = report["group"]
    for g in report["groups"]:
        agents = sorted(g["agents"])
        agent = g.get("agent") or (g["key"] if group == "agent" else "+".join(a for a in agents if a))
        project = g.get("project") or (g["key"] if group == "project" else "")
        w.writerow((group, g["key"], agent, project, g["turns"], *(g["tokens"][k] for k in TOKEN_FIELDS),
                    g["total_tokens"], "" if g["cost"] is None else f"{g['cost']:.6f}", int(g["cost_partial"])))
    return out.getvalue()


def doctor_summary(data_dir, days: int = DEFAULT_DAYS) -> Dict:
    """Tokens e custo dos últimos `days` dias por agente, lidos do índice só leitura (para o --doctor)."""
    from vulcan_celox.core.agents.index import index_path
    path = index_path(data_dir)
    start, end = period(None, None)
    start = end - timedelta(days=days - 1)
    if not Path(path).is_file():
        return {"dias": days, "agentes": {}, "total": None}
    since, until = utc_bounds(start, end)
    try:
        db = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        try:
            rows = [dict(r) for r in db.execute(
                "SELECT u.*, s.project AS project FROM agent_usage u LEFT JOIN sessions s ON s.id = u.session_id "
                "WHERE u.at >= ? AND u.at < ?", (since, until))]
        finally:
            db.close()
    except sqlite3.Error as exc:
        return {"dias": days, "agentes": {}, "total": None, "erro": str(exc)}
    table, _ = pricing.load(data_dir)
    report = aggregate(rows, table, "agent", start, end)
    agents = {g["key"]: {"tokens": g["total_tokens"], "custo_usd": g["cost"], "parcial": g["cost_partial"]}
              for g in report["groups"]}
    t = report["total"]
    return {"dias": days, "agentes": agents,
            "total": {"tokens": t["total_tokens"], "custo_usd": t["cost"], "parcial": t["cost_partial"]},
            "nota": tr("estimativa no preço da API; assinatura cobra de outro jeito")}
