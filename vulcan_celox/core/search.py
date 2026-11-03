"""Busca global em sites, tarefas, notas e tags."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from vulcan_celox.core.textutil import normalize

KIND_ORDER = ("site", "task", "note", "tag")
KIND_LABELS = {"site": "Projetos", "task": "Tarefas", "note": "Post-its", "tag": "Tags"}
SNIPPET_RADIUS = 40


@dataclass
class Hit:
    kind: str
    key: str  # nome do site ou id do item
    site: Optional[str]
    title: str
    snippet: str
    score: float


def _score(title: str, body: str, q: str) -> float:
    t = normalize(title)
    if t == q:
        return 3.0
    if t.startswith(q):
        return 2.0
    if q in t:
        return 1.5
    if q in normalize(body):
        return 1.0
    return 0.0


def _snippet(text: str, q: str) -> str:
    flat = " ".join(text.split())
    idx = normalize(flat).find(q)
    if idx < 0:
        return flat[:SNIPPET_RADIUS * 2]
    start = max(0, idx - SNIPPET_RADIUS)
    end = min(len(flat), idx + len(q) + SNIPPET_RADIUS)
    return ("…" if start else "") + flat[start:end] + ("…" if end < len(flat) else "")


def search(query: str, sites: Iterable, notebook, limit: int = 60) -> List[Hit]:
    q = normalize(query.strip())
    if not q:
        return []
    hits: List[Hit] = []
    for site in sites:
        s = _score(site.name, site.path, q)
        if s:
            hits.append(Hit("site", site.name, site.name, site.name, site.path, s))
    for task in notebook.tasks:
        s = _score(task.title, "", q)
        if s:
            hits.append(Hit("task", task.id, task.site, task.title, task.site or "Global", s))
    for note in notebook.notes:
        s = _score(note.title, note.text, q)
        if s:
            hits.append(Hit("note", note.id, note.site, note.title or "(sem título)", _snippet(note.text, q), s))
    for tag in notebook.tags.values():
        s = _score(tag.name, "", q)
        if s:
            hits.append(Hit("tag", tag.id, None, tag.name, "tag", s))
    hits.sort(key=lambda h: (KIND_ORDER.index(h.kind), -h.score, normalize(h.title)))
    return hits[:limit]
