"""Widgets reutilizáveis: chips de tag, campo de tag com autocomplete, área rolável."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable, List, Optional, Tuple

from vulcan_celox.ui import theme


def text_color_for(bg: str) -> str:
    """Preto ou branco conforme a luminância do fundo (#rrggbb)."""
    try:
        r, g, b = (int(bg[i:i + 2], 16) for i in (1, 3, 5))
    except (ValueError, IndexError):
        return "white"
    return "#111111" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "white"


class ChipBar(tk.Frame):
    """Linha de chips coloridos. on_click(tag_id) e on_remove(tag_id) opcionais."""

    def __init__(self, master, bg: str = theme.BG, on_click: Optional[Callable[[str], None]] = None,
                 on_remove: Optional[Callable[[str], None]] = None):
        super().__init__(master, bg=bg)
        self._bg = bg
        self.on_click = on_click
        self.on_remove = on_remove

    def set_chips(self, specs: Iterable[Tuple[str, str, str]]) -> None:
        for child in self.winfo_children():
            child.destroy()
        for tag_id, name, color in specs:
            fg = text_color_for(color)
            chip = tk.Frame(self, bg=color)
            chip.pack(side="left", padx=(0, 4), pady=1)
            label = tk.Label(chip, text=f" {name} ", bg=color, fg=fg, font=theme.FONT_SMALL, cursor="hand2")
            label.pack(side="left")
            if self.on_click:
                label.bind("<Button-1>", lambda _e, t=tag_id: self.on_click(t))
            if self.on_remove:
                x = tk.Label(chip, text="×", bg=color, fg=fg, font=theme.FONT_SMALL, cursor="hand2")
                x.pack(side="left", padx=(0, 3))
                x.bind("<Button-1>", lambda _e, t=tag_id: self.on_remove(t))


class TagEntry(ttk.Combobox):
    """Combobox com autocomplete por prefixo; Enter chama on_submit(nome)."""

    def __init__(self, master, names_provider: Callable[[], List[str]],
                 on_submit: Callable[[str], None], width: int = 14):
        self.var = tk.StringVar()
        super().__init__(master, textvariable=self.var, width=width)
        self.names_provider = names_provider
        self.on_submit = on_submit
        self.bind("<KeyRelease>", self._filter)
        self.bind("<Return>", self._submit)
        self.bind("<<ComboboxSelected>>", self._submit)
        self.bind("<FocusIn>", self._filter)

    def _filter(self, event=None) -> None:
        if event is not None and getattr(event, "keysym", "") in ("Return", "Up", "Down"):
            return
        prefix = self.var.get().strip().casefold()
        names = self.names_provider()
        self["values"] = [n for n in names if n.casefold().startswith(prefix)] if prefix else names

    def _submit(self, _event=None) -> None:
        name = self.var.get().strip()
        if name:
            self.on_submit(name)
        self.var.set("")


class ScrollFrame(ttk.Frame):
    """Frame com rolagem vertical; conteúdo em self.inner."""

    def __init__(self, master, bg: str = theme.BG):
        super().__init__(master)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")
        for widget in (self.canvas, self.inner):
            widget.bind("<MouseWheel>", self._wheel)

    def _wheel(self, event) -> None:
        # Tk 9 usa múltiplos de 120 por passo; Tk 8.6 no macOS entrega passos pequenos
        delta = event.delta
        steps = -int(delta / 120) if abs(delta) >= 120 else -delta
        if steps:
            self.canvas.yview_scroll(steps, "units")

    def bind_wheel(self, widget) -> None:
        widget.bind("<MouseWheel>", self._wheel)
