"""Lista lateral: item Global fixo e sites agrupados por tipo."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional

from vulcan_celox.core.sites import KIND_ORDER, Site
from vulcan_celox.ui import theme

GLOBAL_IID = "global"
SECTION_LABELS = {"lerd": "LERD", "linked": "LINKED", "parked": "PARKED", "manual": "MANUAL"}


def site_iid(name: str) -> str:
    return f"site:{name}"


class Sidebar(ttk.Frame):
    """Emite on_select(site_name | None) quando a seleção muda (None = Global)."""

    def __init__(self, master, on_select: Callable[[Optional[str]], None],
                 on_add: Callable[[], None], on_remove: Callable[[], None],
                 on_reload: Callable[[], None], on_browser: Callable[[], None],
                 on_terminal: Callable[[], None]):
        super().__init__(master, style="Panel.TFrame", width=260)
        self.pack_propagate(False)
        self.on_select = on_select
        self._sites: Dict[str, Site] = {}
        self._suppress = False

        ttk.Label(self, text="PROJECTS", style="Section.TLabel").pack(anchor="w", padx=12, pady=(12, 4))

        frame = ttk.Frame(self, style="Panel.TFrame")
        frame.pack(fill="both", expand=True, padx=(8, 0))
        self.tree = ttk.Treeview(frame, columns=("progress",), show="tree", selectmode="browse")
        self.tree.column("#0", width=170, stretch=True)
        self.tree.column("progress", width=60, anchor="e", stretch=False)
        self.tree.tag_configure("section", foreground=theme.FG_DIM, font=theme.FONT_SMALL)
        self.tree.tag_configure("global", font=theme.FONT_BOLD)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        buttons = ttk.Frame(self, style="Panel.TFrame")
        buttons.pack(fill="x", padx=8, pady=8)
        for text, cmd, side in (("＋", on_add, "left"), ("－", on_remove, "left"),
                                ("⟳", on_reload, "left"), ("Terminal", on_terminal, "right"),
                                ("Open", on_browser, "right")):
            ttk.Button(buttons, text=text, command=cmd, style="Small.TButton").pack(side=side, padx=2)

    # ── dados ────────────────────────────────────────────────────────────
    def set_sites(self, sites: List[Site], progress: Optional[Dict[Optional[str], str]] = None) -> None:
        selected = self.selected_key()
        had_selection = bool(self.tree.selection())
        self._suppress = True
        try:
            self.tree.delete(*self.tree.get_children())
            self._sites = {s.name: s for s in sites}
            progress = progress or {}
            self.tree.insert("", "end", iid=GLOBAL_IID, text="  Global",
                             values=(progress.get(None, ""),), tags=("global",))
            for kind in KIND_ORDER:
                group = [s for s in sites if s.kind == kind]
                if not group:
                    continue
                sec = f"sec:{kind}"
                self.tree.insert("", "end", iid=sec, text=SECTION_LABELS[kind], open=True,
                                 tags=("section",))
                for site in group:
                    self.tree.insert(sec, "end", iid=site_iid(site.name), text=f"  {site.name}",
                                     values=(progress.get(site.name, ""),))
            if had_selection:
                self.select(selected)
        finally:
            self._suppress = False

    def update_progress(self, progress: Dict[Optional[str], str]) -> None:
        if self.tree.exists(GLOBAL_IID):
            self.tree.set(GLOBAL_IID, "progress", progress.get(None, ""))
        for name in self._sites:
            iid = site_iid(name)
            if self.tree.exists(iid):
                self.tree.set(iid, "progress", progress.get(name, ""))

    def site(self, name: Optional[str]) -> Optional[Site]:
        return self._sites.get(name) if name else None

    # ── seleção ──────────────────────────────────────────────────────────
    def selected_key(self) -> Optional[str]:
        sel = self.tree.selection()
        if not sel or sel[0] == GLOBAL_IID or not sel[0].startswith("site:"):
            return None
        return sel[0][len("site:"):]

    def select(self, name: Optional[str]) -> None:
        iid = site_iid(name) if name and self.tree.exists(site_iid(name)) else GLOBAL_IID
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.see(iid)

    def _on_tree_select(self, _event=None) -> None:
        if self._suppress:
            return
        sel = self.tree.selection()
        if sel and sel[0].startswith("sec:"):
            self.select(None)
            return
        self.on_select(self.selected_key())
