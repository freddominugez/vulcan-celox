"""Modelos do caderno de produtividade: Tag, Note e Task."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

NOTE_COLORS = ("amarelo", "rosa", "verde", "azul", "laranja", "roxo")
# sem o acento da interface nem as cores de estado (verde, âmbar, vermelho)
TAG_COLORS = ("#6ea8fe", "#a78bfa", "#f472b6", "#2dd4bf", "#c4a484", "#93c5fd", "#e879f9", "#a1a1aa")
# paleta da v0.1: cada cor antiga vira a cor nova na mesma posição ao carregar
LEGACY_TAG_COLORS = ("#f53003", "#e8b339", "#4cc38a", "#3fa7f5", "#a86cf0", "#f06cb4", "#36c5c5", "#9a9ba3")
STATUSES = ("todo", "doing", "done")
STATUS_LABELS = {"todo": "A fazer", "doing": "Em andamento", "done": "Concluída"}
PRIORITY_LABELS = {1: "Alta", 2: "Média", 3: "Baixa"}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id() -> str:
    return uuid.uuid4().hex


def _from_dict(cls, data: Optional[Dict[str, Any]]):
    """Constrói a dataclass ignorando chaves desconhecidas e usando defaults nas ausentes."""
    data = data if isinstance(data, dict) else {}
    names = {f.name for f in fields(cls)}
    obj = cls(**{k: v for k, v in data.items() if k in names})
    return obj


@dataclass
class Tag:
    id: str = field(default_factory=new_id)
    name: str = ""
    color: str = TAG_COLORS[0]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data) -> "Tag":
        tag = _from_dict(cls, data)
        tag.name = str(tag.name or "")
        if tag.color in LEGACY_TAG_COLORS:
            tag.color = TAG_COLORS[LEGACY_TAG_COLORS.index(tag.color)]
        return tag


@dataclass
class Note:
    id: str = field(default_factory=new_id)
    site: Optional[str] = None
    text: str = ""
    color: str = "amarelo"
    tags: List[str] = field(default_factory=list)
    pinned: bool = False
    order: int = 0
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    terminal: Optional[str] = None  # id da sessão de terminal

    @property
    def title(self) -> str:
        for line in self.text.splitlines():
            if line.strip():
                return line.strip()
        return ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data) -> "Note":
        note = _from_dict(cls, data)
        if note.color not in NOTE_COLORS:
            note.color = "amarelo"
        note.tags = [t for t in (note.tags or []) if isinstance(t, str)]
        note.text = str(note.text or "")
        note.terminal = note.terminal if isinstance(note.terminal, str) and note.terminal else None
        return note


@dataclass
class Task:
    id: str = field(default_factory=new_id)
    site: Optional[str] = None
    title: str = ""
    status: str = "todo"
    priority: int = 2
    tags: List[str] = field(default_factory=list)
    due: Optional[str] = None
    order: int = 0
    created_at: str = field(default_factory=now_iso)
    done_at: Optional[str] = None
    terminal: Optional[str] = None  # id da sessão de terminal
    assignee: Optional[str] = None  # responsável, texto livre

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data) -> "Task":
        task = _from_dict(cls, data)
        if task.status not in STATUSES:
            task.status = "todo"
        try:
            task.priority = min(3, max(1, int(task.priority)))
        except (TypeError, ValueError):
            task.priority = 2
        task.tags = [t for t in (task.tags or []) if isinstance(t, str)]
        task.title = str(task.title or "")
        task.terminal = task.terminal if isinstance(task.terminal, str) and task.terminal else None
        task.assignee = clean_assignee(task.assignee)
        return task


ASSIGNEE_MAX = 60


def clean_assignee(value) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())[:ASSIGNEE_MAX]
    return value or None
