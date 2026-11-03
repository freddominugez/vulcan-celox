"""Janela de busca global (Cmd+K)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Iterable

from vulcan_celox.core.i18n import tr
from vulcan_celox.core.search import KIND_LABELS, KIND_ORDER, Hit, search
from vulcan_celox.ui import theme


class SearchWindow(tk.Toplevel):
    def __init__(self, master, sites_provider: Callable[[], Iterable], notebook,
                 on_open: Callable[[Hit], None]):
        super().__init__(master)
        self.title("Search")
        self.configure(bg=theme.BG)
        self.geometry("620x460")
        self.transient(master)
        self.sites_provider = sites_provider
        self.notebook = notebook
        self.on_open = on_open
        self.hits: Dict[str, Hit] = {}

        self.var_query = tk.StringVar()
        entry = ttk.Entry(self, textvariable=self.var_query, font=theme.FONT_TITLE)
        entry.pack(fill="x", padx=14, pady=(14, 8))
        entry.bind("<KeyRelease>", self._on_key)
        entry.bind("<Return>", lambda _e: self.open_selected())
        entry.bind("<Down>", lambda _e: self._move(1))
        entry.bind("<Up>", lambda _e: self._move(-1))
        entry.bind("<Escape>", lambda _e: self.destroy())
        self.entry = entry

        self.tree = ttk.Treeview(self, columns=("detalhe",), show="tree", selectmode="browse")
        self.tree.column("#0", width=300)
        self.tree.column("detalhe", width=280)
        self.tree.tag_configure("group", foreground=theme.FG_DIM, font=theme.FONT_SMALL)
        self.tree.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.tree.bind("<Double-1>", lambda _e: self.open_selected())
        self.tree.bind("<Return>", lambda _e: self.open_selected())
        self.bind("<Escape>", lambda _e: self.destroy())
        entry.focus_set()

    def _on_key(self, event) -> None:
        if event.keysym in ("Return", "Up", "Down", "Escape"):
            return
        self.run_query()

    def run_query(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.hits = {}
        hits = search(self.var_query.get(), list(self.sites_provider()), self.notebook)
        first = None
        for kind in KIND_ORDER:
            group = [h for h in hits if h.kind == kind]
            if not group:
                continue
            parent = self.tree.insert("", "end", iid=f"group:{kind}", text=f"{tr(KIND_LABELS[kind])} ({len(group)})",
                                      open=True, tags=("group",))
            for hit in group:
                iid = f"{hit.kind}:{hit.key}"
                self.tree.insert(parent, "end", iid=iid, text=f"  {hit.title}", values=(hit.snippet,))
                self.hits[iid] = hit
                first = first or iid
        if first:
            self.tree.selection_set(first)

    def _move(self, delta: int) -> None:
        items = list(self.hits)
        if not items:
            return
        sel = self.tree.selection()
        idx = items.index(sel[0]) if sel and sel[0] in items else -1
        target = items[max(0, min(len(items) - 1, idx + delta))]
        self.tree.selection_set(target)
        self.tree.see(target)

    def open_selected(self) -> None:
        sel = self.tree.selection()
        hit = self.hits.get(sel[0]) if sel else None
        if hit is None:
            return
        self.destroy()
        self.on_open(hit)
