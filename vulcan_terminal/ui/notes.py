"""Quadro de post-its de um site (ou Global)."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict, Optional

from vulcan_terminal.core.debounce import Debouncer
from vulcan_terminal.core.models import Note
from vulcan_terminal.core.notebook import Notebook, chip_specs
from vulcan_terminal.ui import theme
from vulcan_terminal.ui.widgets import ChipBar, ScrollFrame, TagEntry

COLUMNS = 3
ALL_TAGS = "Todas as tags"
AUTOSAVE_SECONDS = 0.5
POLL_MS = 100


class PostItCard(tk.Frame):
    def __init__(self, board: "NotesBoard", note: Note):
        bg, fg = theme.NOTE_COLORS.get(note.color, theme.NOTE_COLORS["amarelo"])
        super().__init__(board.grid_frame, bg=bg, highlightthickness=1, highlightbackground=theme.NOTE_BORDER)
        self.board = board
        self.note_id = note.id

        top = tk.Frame(self, bg=bg)
        top.pack(fill="x", padx=6, pady=(5, 0))
        self.handle = tk.Label(top, text="⋮⋮", bg=bg, fg=fg, cursor="fleur", font=theme.FONT_BOLD)
        self.handle.pack(side="left")
        self.handle.bind("<ButtonPress-1>", self._drag_start)
        self.handle.bind("<ButtonRelease-1>", self._drag_end)

        def icon(text, command, tip_side="right"):
            lbl = tk.Label(top, text=text, bg=bg, fg=fg, cursor="hand2", font=theme.FONT)
            lbl.pack(side=tip_side, padx=3)
            lbl.bind("<Button-1>", lambda _e: command())
            return lbl

        icon("×", self._delete)
        icon("●", lambda: board.notebook.cycle_note_color(self.note_id))
        icon("★" if note.pinned else "☆",
             lambda: board.notebook.update_note(self.note_id, pinned=not board.notebook.note(self.note_id).pinned))

        self.text = tk.Text(self, width=26, height=7, bg=bg, fg=fg, bd=0, highlightthickness=0,
                            wrap="word", font=theme.FONT, insertbackground=fg, undo=True)
        self.text.pack(fill="both", expand=True, padx=8, pady=4)
        self.text.insert("1.0", note.text)
        self.text.edit_modified(False)
        self.text.bind("<<Modified>>", self._on_modified)
        self.text.bind("<Command-s>", lambda _e: board.flush())
        board.scroll.bind_wheel(self.text)

        bottom = tk.Frame(self, bg=bg)
        bottom.pack(fill="x", padx=6, pady=(0, 6))
        self.chips = ChipBar(bottom, bg=bg, on_remove=self._remove_tag)
        self.chips.pack(side="left", fill="x", expand=True)
        self.chips.set_chips(chip_specs(note, board.notebook.tags))
        self.tag_entry = TagEntry(bottom, names_provider=board.tag_names, on_submit=self._add_tag, width=9)
        self.tag_entry.pack(side="right")

    # ── edição ───────────────────────────────────────────────────────────
    def _on_modified(self, _event=None) -> None:
        if self.text.edit_modified():
            self.board.queue_text(self.note_id, self.text.get("1.0", "end-1c"))
            self.text.edit_modified(False)

    def _add_tag(self, name: str) -> None:
        note = self.board.notebook.note(self.note_id)
        if note:
            self.board.flush()
            self.board.notebook.add_tag_to_item(note, name)

    def _remove_tag(self, tag_id: str) -> None:
        note = self.board.notebook.note(self.note_id)
        if note:
            self.board.flush()
            self.board.notebook.remove_tag_from_item(note, tag_id)

    def _delete(self) -> None:
        note = self.board.notebook.note(self.note_id)
        if note is None:
            return
        if note.text.strip() and not messagebox.askyesno("Post-it", "Apagar este post-it?", parent=self):
            return
        self.board.flush()
        self.board.notebook.delete_note(self.note_id)

    # ── arrastar para reordenar ──────────────────────────────────────────
    def _drag_start(self, _event) -> None:
        self.board.dragging = self.note_id
        self.configure(highlightbackground=theme.ACCENT, highlightthickness=2)

    def _drag_end(self, event) -> None:
        self.configure(highlightbackground=theme.NOTE_BORDER, highlightthickness=1)
        source = self.board.dragging
        self.board.dragging = None
        target = self.winfo_containing(event.x_root, event.y_root)
        while target is not None and not isinstance(target, PostItCard):
            target = target.master
        if source and isinstance(target, PostItCard) and target.note_id != source:
            self.board.move(source, target.note_id)


class NotesBoard(ttk.Frame):
    def __init__(self, master, notebook: Notebook, site: Optional[str]):
        super().__init__(master)
        self.notebook = notebook
        self.site = site
        self.dragging: Optional[str] = None
        self._pending: Dict[str, str] = {}
        self._saving = False
        self.debouncer = Debouncer(AUTOSAVE_SECONDS, self._write_pending)

        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(6, 8))
        ttk.Button(bar, text="+ Novo post-it", style="Accent.TButton", command=self.new_note).pack(side="left")
        self.var_query = tk.StringVar()
        search = ttk.Entry(bar, textvariable=self.var_query, width=24)
        search.pack(side="left", padx=(12, 6))
        search.bind("<KeyRelease>", lambda _e: self.render())
        ttk.Label(bar, text="buscar", style="Dim.TLabel").pack(side="left")
        self.var_tag = tk.StringVar(value=ALL_TAGS)
        self.tag_filter = ttk.Combobox(bar, textvariable=self.var_tag, state="readonly", width=18)
        self.tag_filter.pack(side="right")
        self.tag_filter.bind("<<ComboboxSelected>>", lambda _e: self.render())
        ttk.Label(bar, text="⋮⋮ arrasta · ☆ fixa · ● cor · salva sozinho", style="Dim.TLabel").pack(side="right", padx=12)

        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True)
        self.grid_frame = self.scroll.inner
        for col in range(COLUMNS):
            self.grid_frame.columnconfigure(col, weight=1, uniform="notes")

        self._unsubscribe = notebook.subscribe(self._on_notebook_change)
        self.bind("<Destroy>", self._on_destroy)
        self.render()
        self.after(POLL_MS, self._poll)

    # ── dados ────────────────────────────────────────────────────────────
    def tag_names(self):
        return [t.name for t in self.notebook.sorted_tags()]

    def _selected_tag_id(self) -> Optional[str]:
        name = self.var_tag.get()
        tag = self.notebook.tag_by_name(name) if name != ALL_TAGS else None
        return tag.id if tag else None

    def queue_text(self, note_id: str, text: str) -> None:
        self._pending[note_id] = text
        self.debouncer.touch()

    def _write_pending(self) -> None:
        if not self._pending:
            return
        pending, self._pending = self._pending, {}
        self._saving = True
        try:
            for note_id, text in pending.items():
                if self.notebook.note(note_id):
                    self.notebook.update_note(note_id, save=False, text=text)
            self.notebook.changed("notes")
        finally:
            self._saving = False

    def flush(self) -> None:
        self.debouncer.flush()

    def _poll(self) -> None:
        if not self.winfo_exists():
            return
        self.debouncer.poll()
        self.after(POLL_MS, self._poll)

    def _on_notebook_change(self, kind: str) -> None:
        if self._saving or kind not in ("notes", "tags", "all"):
            return  # gravação do próprio texto: não redesenha para não perder o cursor
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        self.render()

    def _on_destroy(self, event) -> None:
        if event.widget is self:
            self.flush()
            self._unsubscribe()

    # ── ações ────────────────────────────────────────────────────────────
    def new_note(self) -> Note:
        self.flush()
        tag_id = self._selected_tag_id()
        note = self.notebook.add_note(self.site, "", tags=[tag_id] if tag_id else None)
        card = self.cards.get(note.id)
        if card is not None:
            card.text.focus_set()
        return note

    def move(self, source_id: str, target_id: str) -> None:
        self.flush()
        ordered = [n.id for n in self.notebook.notes_for(self.site)]
        if target_id in ordered:
            self.notebook.reorder_note(source_id, ordered.index(target_id))

    # ── desenho ──────────────────────────────────────────────────────────
    def render(self) -> None:
        self.tag_filter["values"] = [ALL_TAGS, *self.tag_names()]
        if self.var_tag.get() != ALL_TAGS and not self.notebook.tag_by_name(self.var_tag.get()):
            self.var_tag.set(ALL_TAGS)
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.cards: Dict[str, PostItCard] = {}
        notes = self.notebook.notes_for(self.site, self.var_query.get(), self._selected_tag_id())
        if not notes:
            empty = "Nenhum post-it encontrado." if self.var_query.get() or self._selected_tag_id() \
                else "Nenhum post-it ainda. Clique em + Novo post-it."
            tk.Label(self.grid_frame, text=empty, bg=theme.BG, fg=theme.FG_DIM,
                     font=theme.FONT).grid(row=0, column=0, columnspan=COLUMNS, pady=40)
            return
        for i, note in enumerate(notes):
            card = PostItCard(self, note)
            card.grid(row=i // COLUMNS, column=i % COLUMNS, padx=8, pady=8, sticky="nsew")
            self.cards[note.id] = card
