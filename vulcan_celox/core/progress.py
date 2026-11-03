"""Cálculo de progresso das tarefas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from vulcan_celox.core.i18n import tr

EMPTY_LABEL = "sem tarefas"
BAR_WIDTH = 10


@dataclass(frozen=True)
class Progress:
    total: int = 0
    done: int = 0
    doing: int = 0

    @property
    def todo(self) -> int:
        return self.total - self.done - self.doing

    @property
    def pct(self) -> int:
        """Percentual inteiro 0..100, arredondando meio para cima."""
        if self.total <= 0:
            return 0
        return (self.done * 200 + self.total) // (self.total * 2)

    @property
    def label(self) -> str:
        return tr(EMPTY_LABEL) if self.total == 0 else f"{self.done}/{self.total} · {self.pct}%"

    @property
    def short(self) -> str:
        return "" if self.total == 0 else f"{self.done}/{self.total}"


def progress(tasks: Iterable) -> Progress:
    total = done = doing = 0
    for task in tasks:
        total += 1
        if task.status == "done":
            done += 1
        elif task.status == "doing":
            doing += 1
    return Progress(total, done, doing)


def progress_by_site(tasks: Iterable) -> Dict[Optional[str], Progress]:
    groups: Dict[Optional[str], list] = {}
    for task in tasks:
        groups.setdefault(task.site, []).append(task)
    return {site: progress(items) for site, items in groups.items()}


def progress_by_tag(tasks: Iterable) -> Dict[str, Progress]:
    groups: Dict[str, list] = {}
    for task in tasks:
        for tag_id in task.tags:
            groups.setdefault(tag_id, []).append(task)
    return {tag_id: progress(items) for tag_id, items in groups.items()}


def text_bar(pct: int, width: int = BAR_WIDTH) -> str:
    filled = max(0, min(width, pct * width // 100))
    return "█" * filled + "░" * (width - filled)
