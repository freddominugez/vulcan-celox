"""Janela de gerenciamento de tags."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from vulcan_terminal.core.models import TAG_COLORS
from vulcan_terminal.core.notebook import DuplicateTag, Notebook
from vulcan_terminal.core.progress import progress_by_tag
from vulcan_terminal.ui import theme


class TagManager(tk.Toplevel):
    def __init__(self, master, notebook: Notebook):
        super().__init__(master)
        self.title("Tags")
        self.configure(bg=theme.BG)
        self.geometry("420x440")
        self.transient(master)
        self.notebook = notebook

        ttk.Label(self, text="Tags", style="Title.TLabel").pack(anchor="w", padx=14, pady=(12, 6))

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=14)
        self.tree = ttk.Treeview(frame, columns=("uso", "progresso"), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Nome")
        self.tree.heading("uso", text="Itens")
        self.tree.heading("progresso", text="Tarefas")
        self.tree.column("uso", width=50, anchor="e", stretch=False)
        self.tree.column("progresso", width=110, anchor="e", stretch=False)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        form = ttk.Frame(self)
        form.pack(fill="x", padx=14, pady=8)
        self.var_name = tk.StringVar()
        entry = ttk.Entry(form, textvariable=self.var_name)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _e: self.create())
        ttk.Button(form, text="Nova", style="Accent.TButton", command=self.create).pack(side="left", padx=(6, 0))

        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=14, pady=(0, 12))
        ttk.Button(actions, text="Renomear", command=self.rename).pack(side="left")
        ttk.Button(actions, text="Trocar cor", command=self.cycle_color).pack(side="left", padx=6)
        ttk.Button(actions, text="Excluir", command=self.delete).pack(side="right")

        self._unsubscribe = notebook.subscribe(lambda _k: self.refresh())
        self.bind("<Destroy>", self._on_destroy)
        self.refresh()

    def _on_destroy(self, event) -> None:
        if event.widget is self:
            self._unsubscribe()

    def selected_id(self) -> Optional[str]:
        sel = self.tree.selection()
        return sel[0] if sel else None

    def refresh(self) -> None:
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        selected = self.selected_id()
        self.tree.delete(*self.tree.get_children())
        usage = {}
        for item in [*self.notebook.notes, *self.notebook.tasks]:
            for tag_id in item.tags:
                usage[tag_id] = usage.get(tag_id, 0) + 1
        by_tag = progress_by_tag(self.notebook.tasks)
        for tag in self.notebook.sorted_tags():
            self.tree.tag_configure(f"c{tag.id}", foreground=tag.color)
            tag_progress = by_tag[tag.id].label if tag.id in by_tag else ""
            self.tree.insert("", "end", iid=tag.id, text=f"●  {tag.name}",
                             values=(usage.get(tag.id, 0), tag_progress), tags=(f"c{tag.id}",))
        if selected and self.tree.exists(selected):
            self.tree.selection_set(selected)

    def _on_select(self, _event=None) -> None:
        tag_id = self.selected_id()
        if tag_id and tag_id in self.notebook.tags:
            self.var_name.set(self.notebook.tags[tag_id].name)

    def create(self) -> None:
        try:
            tag = self.notebook.create_tag(self.var_name.get())
        except DuplicateTag:
            messagebox.showwarning("Tags", "Já existe uma tag com esse nome.", parent=self)
            return
        except ValueError:
            return
        self.var_name.set("")
        self.tree.selection_set(tag.id)

    def rename(self) -> None:
        tag_id = self.selected_id()
        if not tag_id:
            return
        try:
            self.notebook.rename_tag(tag_id, self.var_name.get())
        except DuplicateTag:
            messagebox.showwarning("Tags", "Já existe uma tag com esse nome.", parent=self)
        except ValueError:
            pass

    def cycle_color(self) -> None:
        tag_id = self.selected_id()
        if not tag_id:
            return
        current = self.notebook.tags[tag_id].color
        idx = TAG_COLORS.index(current) if current in TAG_COLORS else -1
        self.notebook.set_tag_color(tag_id, TAG_COLORS[(idx + 1) % len(TAG_COLORS)])

    def delete(self) -> None:
        tag_id = self.selected_id()
        if not tag_id:
            return
        name = self.notebook.tags[tag_id].name
        if messagebox.askyesno("Tags", f"Excluir a tag '{name}'?\nEla sai de todas as notas e tarefas.",
                               parent=self):
            self.notebook.delete_tag(tag_id)
            self.var_name.set("")
