"""Lista de tarefas de um site (ou Global)."""

from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import ttk
from typing import Callable, List, Optional

from vulcan_celox.core.i18n import tr
from vulcan_celox.core.models import PRIORITY_LABELS as _PRIORITY_LABELS
from vulcan_celox.core.notebook import InvalidDue, Notebook, chip_specs
from vulcan_celox.ui import theme
from vulcan_celox.ui.widgets import ChipBar, TagEntry

PRIORITY_LABELS = {key: tr(text) for key, text in _PRIORITY_LABELS.items()}
STATUS_ICONS = {"todo": "○", "doing": "◐", "done": "●"}
STATUS_FILTERS = [("All", None), ("To do", ["todo"]), ("In progress", ["doing"]),
                  ("Done", ["done"]), ("Open", ["todo", "doing"])]
SORTS = [("Priority", "priority"), ("Due date", "due"), ("Manual", "manual")]
ALL_TAGS = "All tags"
UNDO_MS = 5000
COLUMNS = ("status", "prioridade", "titulo", "tags", "prazo")


class TasksPanel(ttk.Frame):
    def __init__(self, master, notebook: Notebook, site: Optional[str],
                 on_message: Callable[[str], None] = lambda _m: None):
        super().__init__(master)
        self.notebook = notebook
        self.site = site
        self.on_message = on_message
        self._pending_tags: List[str] = []
        self._undo_job = None
        self._editor: Optional[ttk.Entry] = None

        self._build_add_row()
        self._build_filters()
        self._build_tree()
        self._build_actions()

        self._unsubscribe = notebook.subscribe(self._on_change)
        self.bind("<Destroy>", self._on_destroy)
        self.render()

    # ── construção ───────────────────────────────────────────────────────
    def _build_add_row(self) -> None:
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(6, 4))
        self.var_title = tk.StringVar()
        title = ttk.Entry(row, textvariable=self.var_title)
        title.pack(side="left", fill="x", expand=True)
        title.bind("<Return>", lambda _e: self.add())
        self.entry_title = title

        self.var_priority = tk.StringVar(value=PRIORITY_LABELS[2])
        ttk.Combobox(row, textvariable=self.var_priority, values=[PRIORITY_LABELS[p] for p in (1, 2, 3)],
                     state="readonly", width=7).pack(side="left", padx=(6, 0))
        self.var_due = tk.StringVar()
        due = ttk.Entry(row, textvariable=self.var_due, width=11)
        due.pack(side="left", padx=(6, 0))
        due.bind("<Return>", lambda _e: self.add())
        self.new_tag_entry = TagEntry(row, names_provider=self._tag_names, on_submit=self._queue_tag, width=10)
        self.new_tag_entry.pack(side="left", padx=(6, 0))
        ttk.Button(row, text="Add", style="Accent.TButton", command=self.add).pack(side="left", padx=(6, 0))

        hint = ttk.Frame(self)
        hint.pack(fill="x")
        ttk.Label(hint, text="title · priority · due date YYYY-MM-DD · tag (Enter adds)",
                  style="Dim.TLabel").pack(side="left")
        self.pending_chips = ChipBar(hint, on_remove=self._unqueue_tag)
        self.pending_chips.pack(side="left", padx=8)

    def _build_filters(self) -> None:
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(8, 4))
        self.var_status = tk.StringVar(value="All")
        self.var_tag = tk.StringVar(value=ALL_TAGS)
        self.var_sort = tk.StringVar(value="Priority")
        for label, var, values, width in (("Status", self.var_status, [s for s, _ in STATUS_FILTERS], 12),
                                          ("Tag", self.var_tag, [ALL_TAGS], 16),
                                          ("Sort", self.var_sort, [s for s, _ in SORTS], 10)):
            ttk.Label(row, text=label, style="Dim.TLabel").pack(side="left", padx=(0, 4))
            box = ttk.Combobox(row, textvariable=var, values=values, state="readonly", width=width)
            box.pack(side="left", padx=(0, 12))
            box.bind("<<ComboboxSelected>>", lambda _e: self.render())
            if var is self.var_tag:
                self.tag_filter = box

    def _build_tree(self) -> None:
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, pady=(4, 0))
        self.tree = ttk.Treeview(frame, columns=COLUMNS, show="headings", selectmode="browse")
        for col, text, width, anchor, stretch in (("status", "", 36, "center", False),
                                                  ("prioridade", "Priority", 84, "w", False),
                                                  ("titulo", "Title", 360, "w", True),
                                                  ("tags", "Tags", 160, "w", False),
                                                  ("prazo", "Due date", 96, "w", False)):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor=anchor, stretch=stretch)
        self.tree.tag_configure("done", foreground=theme.FG_DIM)
        self.tree.tag_configure("doing", foreground=theme.WARN)
        self.tree.tag_configure("late", foreground=theme.ACCENT)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Button-1>", self._on_click, add="+")
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<BackSpace>", lambda _e: self.delete_selected())
        self.tree.bind("<Delete>", lambda _e: self.delete_selected())
        self.tree.bind("<space>", lambda _e: self._cycle_selected())

    def _build_actions(self) -> None:
        row = ttk.Frame(self)
        row.pack(fill="x", pady=6)
        ttk.Button(row, text="↑", style="Small.TButton", command=lambda: self._move(-1)).pack(side="left")
        ttk.Button(row, text="↓", style="Small.TButton", command=lambda: self._move(1)).pack(side="left", padx=4)
        ttk.Button(row, text="Delete", style="Small.TButton", command=self.delete_selected).pack(side="left", padx=(8, 0))
        ttk.Label(row, text="click ○ to change status · double-click to edit",
                  style="Dim.TLabel").pack(side="left", padx=12)
        self.undo_frame = ttk.Frame(row)
        self.undo_label = ttk.Label(self.undo_frame, text="Task deleted.", style="Dim.TLabel")
        self.undo_label.pack(side="left")
        ttk.Button(self.undo_frame, text="Undo", style="Small.TButton", command=self.undo).pack(side="left", padx=6)

    # ── dados ────────────────────────────────────────────────────────────
    def _tag_names(self) -> List[str]:
        return [t.name for t in self.notebook.sorted_tags()]

    def _queue_tag(self, name: str) -> None:
        tag = self.notebook.ensure_tag(name)
        if tag.id not in self._pending_tags:
            self._pending_tags.append(tag.id)
        self._render_pending()

    def _unqueue_tag(self, tag_id: str) -> None:
        self._pending_tags = [t for t in self._pending_tags if t != tag_id]
        self._render_pending()

    def _render_pending(self) -> None:
        tags = self.notebook.tags
        self.pending_chips.set_chips([(t, tags[t].name, tags[t].color) for t in self._pending_tags if t in tags])

    def current_filter(self):
        statuses = dict(STATUS_FILTERS).get(self.var_status.get())
        tag = self.notebook.tag_by_name(self.var_tag.get()) if self.var_tag.get() != ALL_TAGS else None
        sort = dict(SORTS).get(self.var_sort.get(), "priority")
        return statuses, (tag.id if tag else None), sort

    def selected_id(self) -> Optional[str]:
        sel = self.tree.selection()
        return sel[0] if sel else None

    # ── ações ────────────────────────────────────────────────────────────
    def add(self):
        title = self.var_title.get().strip()
        if not title:
            self.entry_title.focus_set()
            return None
        priority = {v: k for k, v in PRIORITY_LABELS.items()}.get(self.var_priority.get(), 2)
        try:
            task = self.notebook.add_task(self.site, title, priority=priority,
                                          tags=list(self._pending_tags), due=self.var_due.get())
        except InvalidDue:
            self.on_message("invalid due date: use YYYY-MM-DD (e.g. 2026-09-30)")
            return None
        self.var_title.set("")
        self.var_due.set("")
        self._pending_tags = []
        self._render_pending()
        self.entry_title.focus_set()
        return task

    def delete_selected(self) -> None:
        task_id = self.selected_id()
        if not task_id:
            return
        task = self.notebook.delete_task(task_id)
        self.undo_label.configure(text=f"Deleted: {task.title[:40]}")
        self.undo_frame.pack(side="right")
        if self._undo_job:
            self.after_cancel(self._undo_job)
        self._undo_job = self.after(UNDO_MS, self._hide_undo)

    def undo(self) -> None:
        task = self.notebook.undo_delete()
        self._hide_undo()
        if task and self.tree.exists(task.id):
            self.tree.selection_set(task.id)

    def _hide_undo(self) -> None:
        self._undo_job = None
        try:
            self.undo_frame.pack_forget()
        except tk.TclError:
            pass

    def _cycle_selected(self) -> None:
        task_id = self.selected_id()
        if task_id:
            self.notebook.cycle_status(task_id)

    def _move(self, delta: int) -> None:
        task_id = self.selected_id()
        if not task_id:
            return
        self.var_sort.set("Manual")
        self.notebook.move_task(task_id, delta)

    def _on_click(self, event) -> None:
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        iid = self.tree.identify_row(event.y)
        if iid and self.tree.identify_column(event.x) == "#1":
            self.notebook.cycle_status(iid)
            if self.tree.exists(iid):
                self.tree.selection_set(iid)

    def _on_double_click(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        task = self.notebook.task(iid) if iid else None
        if task is None:
            return
        if column == "#2":
            self.notebook.cycle_priority(iid)
        elif column == "#3":
            self.edit_cell(iid, column, task.title, lambda v: self.notebook.update_task(iid, title=v))
        elif column == "#4":
            names = ", ".join(name for _, name, _c in chip_specs(task, self.notebook.tags))
            self.edit_cell(iid, column, names, lambda v: self._set_tags_from_text(iid, v))
        elif column == "#5":
            self.edit_cell(iid, column, task.due or "", lambda v: self.notebook.update_task(iid, due=v))

    def _set_tags_from_text(self, task_id: str, text: str) -> None:
        task = self.notebook.task(task_id)
        names = [n.strip() for n in text.split(",") if n.strip()]
        self.notebook.set_item_tags(task, [self.notebook.ensure_tag(n).id for n in names])

    def edit_cell(self, iid: str, column: str, initial: str, commit: Callable[[str], None]) -> Optional[ttk.Entry]:
        self._close_editor()
        bbox = self.tree.bbox(iid, column)
        if not bbox:
            return None
        x, y, w, h = bbox
        entry = ttk.Entry(self.tree)
        entry.place(x=x, y=y, width=max(w, 120), height=h)
        entry.insert(0, initial)
        entry.select_range(0, "end")
        entry.focus_set()
        self._editor = entry

        def done(save: bool):
            if self._editor is not entry:
                return
            value = entry.get()
            self._close_editor()
            if not save:
                return
            try:
                commit(value)
            except InvalidDue:
                self.on_message("invalid due date: use YYYY-MM-DD")
            except ValueError as exc:
                self.on_message(f"not saved: {exc}")

        entry.bind("<Return>", lambda _e: done(True))
        entry.bind("<FocusOut>", lambda _e: done(True))
        entry.bind("<Escape>", lambda _e: done(False))
        entry.commit = lambda: done(True)  # usado pelo selftest
        return entry

    def _close_editor(self) -> None:
        if self._editor is not None:
            editor, self._editor = self._editor, None
            try:
                editor.destroy()
            except tk.TclError:
                pass

    # ── desenho ──────────────────────────────────────────────────────────
    def _on_change(self, kind: str) -> None:
        if kind not in ("tasks", "tags", "all"):
            return
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        self.render()

    def _on_destroy(self, event) -> None:
        if event.widget is self:
            self._unsubscribe()

    def render(self) -> None:
        self.tag_filter["values"] = [ALL_TAGS, *self._tag_names()]
        if self.var_tag.get() != ALL_TAGS and not self.notebook.tag_by_name(self.var_tag.get()):
            self.var_tag.set(ALL_TAGS)
        selected = self.selected_id()
        self.tree.delete(*self.tree.get_children())
        statuses, tag_id, sort = self.current_filter()
        today = date.today().isoformat()
        for task in self.notebook.filter_tasks(self.site, statuses, tag_id, sort):
            names = ", ".join(name for _, name, _c in chip_specs(task, self.notebook.tags))
            row_tags = [task.status]
            if task.status != "done" and task.due and task.due < today:
                row_tags.append("late")
            self.tree.insert("", "end", iid=task.id, tags=row_tags,
                             values=(STATUS_ICONS[task.status], PRIORITY_LABELS[task.priority],
                                     task.title, names, task.due or ""))
        if selected and self.tree.exists(selected):
            self.tree.selection_set(selected)
        self._render_pending()

