"""Caderno de produtividade: tags, notas e tarefas persistidos no Store."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from datetime import date, timedelta

from vulcan_terminal.core.models import NOTE_COLORS, STATUSES, TAG_COLORS, Note, Tag, Task, clean_assignee, now_iso
from vulcan_terminal.core.store import Store, read_json_readonly, write_json_atomic
from vulcan_terminal.core.textutil import contains

LEGACY_MIGRATION = "notes_valetgui_v1"


UNDO_SECONDS = 5.0


class _All:
    def __repr__(self) -> str:
        return "ALL"


ALL = _All()  # filtro "todos os sites" (None já significa Global)


class DuplicateTag(ValueError):
    """Já existe tag com esse nome (comparação sem diferenciar maiúsculas)."""


class InvalidDue(ValueError):
    """Prazo fora do formato AAAA-MM-DD ou data inexistente."""


def validate_due(value: Optional[str]) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    value = str(value).strip()
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise InvalidDue(value) from None
    if len(value) != 10:
        raise InvalidDue(value)
    return value


def validate_priority(value) -> int:
    try:
        priority = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"prioridade inválida: {value}") from None
    if priority not in (1, 2, 3):
        raise ValueError(f"prioridade inválida: {value}")
    return priority


TASK_SORTS = {
    "priority": lambda t: (t.priority, t.due or "9999-12-31", t.order, t.title.casefold()),
    "due": lambda t: (t.due is None, t.due or "", t.priority, t.order),
    "manual": lambda t: (t.order, t.created_at),
    "assignee": lambda t: (t.assignee is None, (t.assignee or "").casefold(), t.due or "9999-12-31", t.priority),
}
NO_ASSIGNEE = "__sem__"
DUE_FILTERS = ("late", "today", "week")


def due_matches(task: Task, when: str, today: date) -> bool:
    if not task.due:
        return False
    iso = today.isoformat()
    if when == "late":
        return task.status != "done" and task.due < iso
    if when == "today":
        return task.due == iso
    if when == "week":
        return iso <= task.due <= (today + timedelta(days=7)).isoformat()
    return True


def task_summary(tasks: List[Task], today: Optional[date] = None) -> Dict[str, int]:
    today = today or date.today()
    open_tasks = [t for t in tasks if t.status != "done"]
    return {"total": len(tasks), "open": len(open_tasks), "done": len(tasks) - len(open_tasks),
            "late": sum(1 for t in open_tasks if due_matches(t, "late", today)),
            "today": sum(1 for t in open_tasks if due_matches(t, "today", today)),
            "unassigned": sum(1 for t in open_tasks if not t.assignee)}


def chip_specs(item, tags: Dict[str, Tag]) -> List[Tuple[str, str, str]]:
    """(id, nome, cor) das tags do item, na ordem do item, ignorando ids órfãos."""
    return [(t, tags[t].name, tags[t].color) for t in item.tags if t in tags]


class Notebook:
    def __init__(self, store: Store, clock: Callable[[], float] = time.monotonic):
        self.store = store
        self.clock = clock
        self._last_deleted: Optional[Tuple[Task, int, float]] = None
        self.tags: Dict[str, Tag] = {}
        self.notes: List[Note] = []
        self.tasks: List[Task] = []
        self._listeners: List[Callable[[str], None]] = []
        self.load()

    # ── persistência ─────────────────────────────────────────────────────
    def load(self) -> None:
        self.tags = {}
        for raw in self.store.load("tags", []):
            tag = Tag.from_dict(raw)
            if tag.name:
                self.tags[tag.id] = tag
        self.notes = [Note.from_dict(raw) for raw in self.store.load("notes", [])]
        self.tasks = [Task.from_dict(raw) for raw in self.store.load("tasks", [])]

    def save(self, kind: str = "all") -> None:
        if kind in ("all", "tags"):
            self.store.save("tags", [t.to_dict() for t in self.tags.values()])
        if kind in ("all", "tags", "notes"):
            self.store.save("notes", [n.to_dict() for n in self.notes])
        if kind in ("all", "tags", "tasks"):
            self.store.save("tasks", [t.to_dict() for t in self.tasks])

    def subscribe(self, listener: Callable[[str], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener) if listener in self._listeners else None

    def changed(self, kind: str) -> None:
        """Persiste e avisa os observadores (kind: tags | notes | tasks | all)."""
        self.save(kind)
        for listener in list(self._listeners):
            listener(kind)

    # ── consultas simples ────────────────────────────────────────────────
    def note(self, note_id: str) -> Optional[Note]:
        return next((n for n in self.notes if n.id == note_id), None)

    def task(self, task_id: str) -> Optional[Task]:
        return next((t for t in self.tasks if t.id == task_id), None)

    def site_keys(self) -> List[Optional[str]]:
        keys = {n.site for n in self.notes} | {t.site for t in self.tasks}
        return sorted(keys, key=lambda k: (k is not None, (k or "").lower()))

    # ── tags ─────────────────────────────────────────────────────────────
    def tag_by_name(self, name: str) -> Optional[Tag]:
        key = name.strip().casefold()
        return next((t for t in self.tags.values() if t.name.casefold() == key), None)

    def sorted_tags(self) -> List[Tag]:
        return sorted(self.tags.values(), key=lambda t: t.name.casefold())

    def create_tag(self, name: str, color: Optional[str] = None) -> Tag:
        name = name.strip()
        if not name:
            raise ValueError("nome de tag vazio")
        if self.tag_by_name(name):
            raise DuplicateTag(name)
        if color is None:
            color = TAG_COLORS[len(self.tags) % len(TAG_COLORS)]
        tag = Tag(name=name, color=color)
        self.tags[tag.id] = tag
        self.changed("tags")
        return tag

    def ensure_tag(self, name: str) -> Tag:
        return self.tag_by_name(name) or self.create_tag(name)

    def rename_tag(self, tag_id: str, name: str) -> Tag:
        tag = self.tags[tag_id]
        name = name.strip()
        if not name:
            raise ValueError("nome de tag vazio")
        other = self.tag_by_name(name)
        if other and other.id != tag_id:
            raise DuplicateTag(name)
        tag.name = name
        self.changed("tags")
        return tag

    def set_tag_color(self, tag_id: str, color: str) -> None:
        self.tags[tag_id].color = color
        self.changed("tags")

    def delete_tag(self, tag_id: str) -> int:
        """Remove a tag e a referência a ela em notas e tarefas. Retorna itens afetados."""
        if tag_id not in self.tags:
            return 0
        del self.tags[tag_id]
        affected = 0
        for item in [*self.notes, *self.tasks]:
            if tag_id in item.tags:
                item.tags = [t for t in item.tags if t != tag_id]
                affected += 1
        self.changed("tags")
        return affected

    def set_item_tags(self, item, tag_ids: List[str]) -> None:
        seen = []
        for tag_id in tag_ids:
            if tag_id in self.tags and tag_id not in seen:
                seen.append(tag_id)
        item.tags = seen
        self.changed("notes" if isinstance(item, Note) else "tasks")

    def add_tag_to_item(self, item, name: str) -> Tag:
        tag = self.ensure_tag(name)
        if tag.id not in item.tags:
            self.set_item_tags(item, [*item.tags, tag.id])
        return tag

    def remove_tag_from_item(self, item, tag_id: str) -> None:
        self.set_item_tags(item, [t for t in item.tags if t != tag_id])

    # ── notas (básico; recursos completos em notes_*) ────────────────────
    def add_note(self, site: Optional[str], text: str = "", color: str = "amarelo",
                 tags: Optional[List[str]] = None, terminal: Optional[str] = None) -> Note:
        same_site = [n.order for n in self.notes if n.site == site]
        note = Note(site=site, text=text, color=color if color in NOTE_COLORS else "amarelo",
                    tags=list(tags or []), order=(max(same_site) + 1) if same_site else 0,
                    terminal=terminal or None)
        self.notes.append(note)
        self.changed("notes")
        return note

    def notes_for(self, site, query: str = "", tag_id: Optional[str] = None,
                  terminal: Optional[str] = None) -> List[Note]:
        """Notas do site (None = Global, ALL = todos): fixadas primeiro, depois pela ordem manual."""
        items = [n for n in self.notes if site is ALL or n.site == site]
        if terminal:
            items = [n for n in items if n.terminal == terminal]
        if query.strip():
            items = [n for n in items if contains(n.text, query.strip())]
        if tag_id:
            items = [n for n in items if tag_id in n.tags]
        return sorted(items, key=lambda n: (not n.pinned, n.order, n.created_at))

    def update_note(self, note_id: str, save: bool = True, **fields) -> Note:
        note = self.note(note_id)
        if note is None:
            raise KeyError(note_id)
        for key, value in fields.items():
            if key == "color" and value not in NOTE_COLORS:
                continue
            if key in ("text", "color", "pinned"):
                setattr(note, key, value)
            if key == "terminal":
                note.terminal = value or None
        note.updated_at = now_iso()
        if save:
            self.changed("notes")
        return note

    def cycle_note_color(self, note_id: str) -> Note:
        note = self.note(note_id)
        idx = NOTE_COLORS.index(note.color) if note.color in NOTE_COLORS else -1
        return self.update_note(note_id, color=NOTE_COLORS[(idx + 1) % len(NOTE_COLORS)])

    def delete_note(self, note_id: str) -> None:
        self.notes = [n for n in self.notes if n.id != note_id]
        self.changed("notes")

    def reorder_note(self, note_id: str, new_index: int = 0, target_id: Optional[str] = None) -> None:
        """Move para `new_index` na lista do site ou, com `target_id`, para a posição daquele post-it."""
        note = self.note(note_id)
        if note is None:
            raise KeyError(note_id)
        ordered = self.notes_for(note.site)
        if target_id is not None:
            target = self.note(target_id)
            if target is None or target.site != note.site:
                raise KeyError(target_id)
            if target is note:
                return
            moving_down = ordered.index(note) < ordered.index(target)
            ordered.remove(note)
            new_index = ordered.index(target) + (1 if moving_down else 0)
        else:
            ordered.remove(note)
        new_index = max(0, min(new_index, len(ordered)))
        ordered.insert(new_index, note)
        for i, item in enumerate(ordered):
            item.order = i
        self.changed("notes")

    # ── tarefas ──────────────────────────────────────────────────────────
    def add_task(self, site: Optional[str], title: str, priority: int = 2,
                 tags: Optional[List[str]] = None, due: Optional[str] = None,
                 terminal: Optional[str] = None, assignee: Optional[str] = None) -> Task:
        title = title.strip()
        if not title:
            raise ValueError("título vazio")
        same_site = [t.order for t in self.tasks if t.site == site]
        task = Task(site=site, title=title, priority=validate_priority(priority),
                    tags=[t for t in (tags or []) if t in self.tags], due=validate_due(due),
                    order=(max(same_site) + 1) if same_site else 0, terminal=terminal or None,
                    assignee=clean_assignee(assignee))
        self.tasks.append(task)
        self.changed("tasks")
        return task

    def update_task(self, task_id: str, **fields) -> Task:
        task = self._task_or_raise(task_id)
        if "title" in fields:
            title = str(fields["title"]).strip()
            if not title:
                raise ValueError("título vazio")
            task.title = title
        if "priority" in fields:
            task.priority = validate_priority(fields["priority"])
        if "due" in fields:
            task.due = validate_due(fields["due"])
        if "status" in fields:
            self._apply_status(task, fields["status"])
        if "terminal" in fields:
            task.terminal = fields["terminal"] or None
        if "assignee" in fields:
            task.assignee = clean_assignee(fields["assignee"])
        self.changed("tasks")
        return task

    def set_status(self, task_id: str, status: str) -> Task:
        return self.update_task(task_id, status=status)

    def cycle_status(self, task_id: str) -> Task:
        task = self._task_or_raise(task_id)
        return self.set_status(task_id, STATUSES[(STATUSES.index(task.status) + 1) % len(STATUSES)])

    def cycle_priority(self, task_id: str) -> Task:
        task = self._task_or_raise(task_id)
        return self.update_task(task_id, priority=task.priority % 3 + 1)

    def delete_task(self, task_id: str) -> Task:
        task = self._task_or_raise(task_id)
        index = self.tasks.index(task)
        self.tasks.remove(task)
        self._last_deleted = (task, index, self.clock())
        self.changed("tasks")
        return task

    def can_undo_delete(self) -> bool:
        last = self._last_deleted
        return last is not None and self.clock() - last[2] <= UNDO_SECONDS

    def undo_delete(self) -> Optional[Task]:
        if not self.can_undo_delete():
            self._last_deleted = None
            return None
        task, index, _ = self._last_deleted
        self._last_deleted = None
        self.tasks.insert(min(index, len(self.tasks)), task)
        self.changed("tasks")
        return task

    def move_task(self, task_id: str, delta: int) -> None:
        """Move na ordem manual dentro do mesmo site."""
        task = self._task_or_raise(task_id)
        ordered = sorted((t for t in self.tasks if t.site == task.site), key=lambda t: t.order)
        i = ordered.index(task)
        j = max(0, min(len(ordered) - 1, i + delta))
        if i == j:
            return
        ordered.insert(j, ordered.pop(i))
        for n, item in enumerate(ordered):
            item.order = n
        self.changed("tasks")

    def filter_tasks(self, site=ALL, statuses: Optional[List[str]] = None,
                     tag_id: Optional[str] = None, sort: str = "priority",
                     terminal: Optional[str] = None, assignee: Optional[str] = None,
                     due: Optional[str] = None, today: Optional[date] = None) -> List[Task]:
        items = [t for t in self.tasks if site is ALL or t.site == site]
        if terminal:
            items = [t for t in items if t.terminal == terminal]
        if assignee == NO_ASSIGNEE:
            items = [t for t in items if not t.assignee]
        elif assignee:
            items = [t for t in items if (t.assignee or "").casefold() == assignee.casefold()]
        if due in DUE_FILTERS:
            items = [t for t in items if due_matches(t, due, today or date.today())]
        if statuses:
            items = [t for t in items if t.status in statuses]
        if tag_id:
            items = [t for t in items if tag_id in t.tags]
        return sorted(items, key=TASK_SORTS.get(sort, TASK_SORTS["priority"]))

    def _task_or_raise(self, task_id: str) -> Task:
        task = self.task(task_id)
        if task is None:
            raise KeyError(task_id)
        return task

    @staticmethod
    def _apply_status(task: Task, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(f"status inválido: {status}")
        if status == "done" and task.status != "done":
            task.done_at = now_iso()
        elif status != "done":
            task.done_at = None
        task.status = status

    # ── exportar / importar ──────────────────────────────────────────────
    def export(self, path) -> Dict[str, int]:
        payload = {
            "schema_version": 1,
            "app": "vulcan-terminal",
            "exported_at": now_iso(),
            "tags": [t.to_dict() for t in self.sorted_tags()],
            "notes": [n.to_dict() for n in self.notes],
            "tasks": [t.to_dict() for t in self.tasks],
        }
        write_json_atomic(Path(path), payload)
        return {k: len(payload[k]) for k in ("tags", "notes", "tasks")}

    def import_(self, path) -> Dict[str, int]:
        """Mescla por id: itens existentes são atualizados, novos são acrescentados.

        Tag importada com nome igual ao de uma tag local (id diferente) é unificada na local.
        """
        data = read_json_readonly(Path(path))
        if not isinstance(data, dict) or data.get("app") != "vulcan-terminal":
            raise ValueError("arquivo não é um caderno exportado pelo Vulcan Terminal")
        counts = {"tags": 0, "notes": 0, "tasks": 0}
        id_map: Dict[str, str] = {}
        for raw in data.get("tags") or []:
            tag = Tag.from_dict(raw)
            if not tag.name:
                continue
            same_name = self.tag_by_name(tag.name)
            if same_name and same_name.id != tag.id:
                id_map[tag.id] = same_name.id
                continue
            self.tags[tag.id] = tag
            counts["tags"] += 1

        def remap(ids):
            out = []
            for t in ids:
                t = id_map.get(t, t)
                if t in self.tags and t not in out:
                    out.append(t)
            return out

        for key, cls, items in (("notes", Note, self.notes), ("tasks", Task, self.tasks)):
            index = {item.id: i for i, item in enumerate(items)}
            for raw in data.get(key) or []:
                item = cls.from_dict(raw)
                item.tags = remap(item.tags)
                if item.id in index:
                    items[index[item.id]] = item
                else:
                    index[item.id] = len(items)
                    items.append(item)
                counts[key] += 1
        self.changed("all")
        return counts

    # ── migração do protótipo ────────────────────────────────────────────
    def migrate_legacy_notes(self) -> int:
        """Converte `legacy_notes` ({site: [{texto, cor}]}) em Note com tag do nome do site."""
        if self.store.migration_done(LEGACY_MIGRATION):
            return 0
        legacy = self.store.load("legacy_notes", {})
        count = 0
        if isinstance(legacy, dict):
            for site, items in legacy.items():
                if not isinstance(site, str) or not isinstance(items, list):
                    continue
                tag = self._ensure_tag_silent(site)
                for order, item in enumerate(items):
                    if not isinstance(item, dict):
                        continue
                    color = item.get("cor", "amarelo")
                    self.notes.append(Note(site=site, text=str(item.get("texto", "")),
                                           color=color if color in NOTE_COLORS else "amarelo",
                                           tags=[tag.id], order=order))
                    count += 1
        if count:
            self.changed("all")
        self.store.mark_migration(LEGACY_MIGRATION)
        return count

    def _ensure_tag_silent(self, name: str) -> Tag:
        for tag in self.tags.values():
            if tag.name.casefold() == name.casefold():
                return tag
        tag = Tag(name=name)
        self.tags[tag.id] = tag
        return tag
