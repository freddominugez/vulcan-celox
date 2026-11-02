"""Eventos da ponte de dumps do Lerd (vt-06): dump(), queries, logs, views e requisições, lidos pela API dele.

Formato conferido em 2026-10-31 no Lerd 1.37.1 (protocolo v1): id, ts, kind, ctx {type, site, branch, domain,
request, pid, rid}, src {file, line}, e `text` (dump) ou `data` (query, log, view, request). Campos novos ou ausentes
não quebram a leitura.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from vulcan_terminal.core.redact import redact

API_FILTERS = ("site", "branch", "kind", "limit")  # os que a API do Lerd aceita; busca de texto é feita no app


def _dict(value) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def parse_event(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    ctx, src = _dict(raw.get("ctx")), _dict(raw.get("src"))
    try:
        line = int(src.get("line") or 0)
    except (TypeError, ValueError):
        line = 0
    return {
        "id": str(raw.get("id") or ""), "ts": str(raw.get("ts") or ""), "kind": str(raw.get("kind") or ""),
        "site": str(ctx.get("site") or ""), "branch": str(ctx.get("branch") or ""), "domain": str(ctx.get("domain") or ""),
        "request": str(ctx.get("request") or ""), "rid": str(ctx.get("rid") or ""), "type": str(ctx.get("type") or ""),
        "file": str(src.get("file") or ""), "line": line, "label": str(raw.get("label") or ""),
        "text": str(raw.get("text") or ""), "data": _dict(raw.get("data")),
    }


def parse_events(rows: Any) -> List[Dict[str, Any]]:
    return [e for e in (parse_event(r) for r in (rows if isinstance(rows, list) else [])) if e]


def event_text(event: Dict[str, Any]) -> str:
    """Texto pesquisável do evento: o dump, o SQL, a mensagem do log ou a view."""
    data = event.get("data") or {}
    parts = [event.get("text", ""), event.get("label", ""), event.get("request", ""), event.get("file", "")]
    for key in ("sql", "message", "name", "view", "context"):
        if isinstance(data.get(key), str):
            parts.append(data[key])
    return "\n".join(p for p in parts if p)


def filter_events(events: List[Dict[str, Any]], site: str = "", branch: str = "", kind: str = "",
                  q: str = "") -> List[Dict[str, Any]]:
    """Filtro combinado (vt-06 C2); a busca de texto passa pelo dump, SQL, mensagem, view, requisição e arquivo."""
    text = (q or "").strip().lower()
    return [e for e in events if (not site or e["site"] == site) and (not branch or e["branch"] == branch)
            and (not kind or e["kind"] == kind) and (not text or text in event_text(e).lower())]


def group_by_request(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Eventos agrupados por requisição (rid do Lerd; sem rid, pela linha da requisição), a mais nova primeiro."""
    groups: Dict[tuple, Dict[str, Any]] = {}
    for e in events:
        key = (e["site"], e["branch"], e["rid"] or f"{e['request']}|{e['ts'][:19]}")
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"rid": e["rid"], "request": e["request"], "site": e["site"], "branch": e["branch"],
                               "ts": e["ts"], "events": [], "counts": {}}
        g["events"].append(e)
        g["counts"][e["kind"]] = g["counts"].get(e["kind"], 0) + 1
        g["ts"] = min(g["ts"], e["ts"]) if g["ts"] else e["ts"]
    for g in groups.values():
        g["events"].sort(key=lambda e: e["ts"])
    return sorted(groups.values(), key=lambda g: g["ts"], reverse=True)


def _ms(event: Dict[str, Any]) -> float:
    try:
        return float((event.get("data") or {}).get("time_ms") or 0)
    except (TypeError, ValueError):
        return 0.0


def group_queries(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Queries idênticas (mesmo SQL) somadas: contagem e tempo total, as mais caras primeiro (vt-06 C3)."""
    found: Dict[str, Dict[str, Any]] = {}
    for e in events:
        if e.get("kind") != "query":
            continue
        sql = str((e.get("data") or {}).get("sql") or "")
        g = found.setdefault(sql, {"sql": sql, "count": 0, "total_ms": 0.0})
        g["count"] += 1
        g["total_ms"] = round(g["total_ms"] + _ms(e), 3)
    return sorted(found.values(), key=lambda g: (-g["count"], -g["total_ms"]))


def filter_min_ms(events: List[Dict[str, Any]], min_ms: float) -> List[Dict[str, Any]]:
    """Tempo mínimo vale só para queries; os outros tipos passam."""
    if not min_ms:
        return list(events)
    return [e for e in events if e.get("kind") != "query" or _ms(e) >= min_ms]


LOG_TONES = {"emergency": "err", "alert": "err", "critical": "err", "error": "err", "warning": "warn",
             "notice": "warn", "info": "info", "debug": "dim"}


def log_tone(level: str) -> str:
    return LOG_TONES.get(str(level or "").lower(), "info")


# vt-06 C4: o que deu erro no site enquanto um agente trabalhava nele
SUMMARY_MAX = 20
SESSION_GRACE = timedelta(minutes=1)  # a última requisição costuma vir logo depois da última resposta do agente


def parse_ts(value: str) -> Optional[datetime]:
    """ISO 8601 com Z ou fuso; frações de qualquer tamanho (o fromisoformat do 3.9 só aceita 3 ou 6 dígitos)."""
    text = (value or "").strip()
    if len(text) < 19:
        return None
    zone = text[19:]
    if zone.startswith("."):
        digits = len(zone) - len(zone[1:].lstrip("0123456789"))
        zone = zone[digits:]
    zone = "+00:00" if zone in ("", "Z", "z") else zone
    try:
        stamp = datetime.fromisoformat(text[:19] + zone)
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def is_error(event: Dict[str, Any]) -> bool:
    if event.get("kind") == "exception":
        return True
    return event.get("kind") == "log" and log_tone((event.get("data") or {}).get("level")) == "err"


def events_for_session(events: Iterable[Dict[str, Any]], site: str, started_at: str,
                       last_activity_at: str) -> List[Dict[str, Any]]:
    start, end = parse_ts(started_at), parse_ts(last_activity_at)
    if not site or not start or not end:
        return []
    end += SESSION_GRACE
    found = []
    for e in events:
        at = parse_ts(e.get("ts", ""))
        if e.get("site") == site and at and start <= at <= end and is_error(e):
            found.append(e)
    return sorted(found, key=lambda e: e["ts"])


def site_for_path(sites: Iterable[Tuple[str, str]], path: str) -> Optional[str]:
    """Site cuja pasta contém a pasta da sessão; o mais específico ganha."""
    if not path:
        return None
    target = os.path.abspath(path)
    best = None
    for name, root in sites:
        if not root:
            continue
        root = os.path.abspath(root)
        if (target == root or target.startswith(root.rstrip(os.sep) + os.sep)) and (best is None or len(root) > len(best[1])):
            best = (name, root)
    return best[0] if best else None


def session_summary(events: List[Dict[str, Any]], site: str) -> str:
    """Texto para colar no agente; passa pelo redact e para em SUMMARY_MAX eventos."""
    lines = [f"Estas exceções e erros aconteceram no site {site} enquanto você trabalhava:"]
    for e in events[:SUMMARY_MAX]:
        data = e.get("data") or {}
        level = str(data.get("level") or e.get("kind") or "").upper()
        message = " ".join(str(data.get("message") or e.get("text") or "").split())[:300]
        where = f" ({'/'.join(e['file'].split('/')[-3:])}:{e['line']})" if e.get("file") else ""
        request = f" em {e['request']}" if e.get("request") else ""
        lines.append(f"- {e.get('ts', '')[11:19]} {level} {message}{where}{request}")
    if len(events) > SUMMARY_MAX:
        lines.append(f"(e mais {len(events) - SUMMARY_MAX} eventos no painel Depuração do Vulcan Terminal)")
    lines.append("Verifique se alguma delas vem das mudanças desta sessão.")
    return redact("\n".join(lines))[0]

