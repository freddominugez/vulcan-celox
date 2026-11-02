"""Paleta, fontes e estilos ttk do Vulcan Terminal."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

BG = "#1e1f24"
BG2 = "#26272e"
BG3 = "#2f3038"
BG_INPUT = "#34353e"
BG_TERM = "#141519"
FG = "#e8e8ec"
FG_DIM = "#9a9ba3"
ACCENT = "#f53003"
ACCENT_ACTIVE = "#d92a02"
OK = "#4cc38a"
WARN = "#e8b339"
BORDER = "#3a3b44"
NOTE_BORDER = "#6b6c75"

FONT = ("Helvetica Neue", 13)
FONT_SMALL = ("Helvetica Neue", 11)
FONT_BOLD = ("Helvetica Neue", 13, "bold")
FONT_TITLE = ("Helvetica Neue", 18, "bold")
FONT_MONO = ("Menlo", 12)

# Post-its: (fundo, texto)
NOTE_COLORS = {
    "amarelo": ("#FFF3A3", "#5c4f12"),
    "rosa": ("#FFC7D6", "#7a2440"),
    "verde": ("#C8F2C2", "#24592a"),
    "azul": ("#BFE3FF", "#1a4468"),
    "laranja": ("#FFD9A8", "#74481a"),
    "roxo": ("#E3CCFF", "#4b2677"),
}


def apply(root: tk.Tk) -> None:
    root.configure(bg=BG)
    root.option_add("*Font", FONT)
    root.option_add("*TCombobox*Listbox.background", BG_INPUT)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)

    st = ttk.Style(root)
    st.theme_use("clam")
    st.configure(".", background=BG, foreground=FG, fieldbackground=BG_INPUT,
                 bordercolor=BORDER, lightcolor=BG3, troughcolor=BG3,
                 selectbackground=ACCENT, selectforeground="white", font=FONT)
    st.configure("TFrame", background=BG)
    st.configure("Panel.TFrame", background=BG2)
    st.configure("Card.TFrame", background=BG3)
    st.configure("TLabel", background=BG, foreground=FG)
    st.configure("Panel.TLabel", background=BG2, foreground=FG)
    st.configure("Dim.TLabel", background=BG, foreground=FG_DIM, font=FONT_SMALL)
    st.configure("PanelDim.TLabel", background=BG2, foreground=FG_DIM, font=FONT_SMALL)
    st.configure("Title.TLabel", background=BG, font=FONT_TITLE)
    st.configure("Brand.TLabel", background=BG2, foreground=FG, font=FONT_TITLE)
    st.configure("Section.TLabel", background=BG2, foreground=FG_DIM, font=FONT_SMALL)

    st.configure("TButton", background=BG3, foreground=FG, padding=(10, 5), borderwidth=0,
                 focusthickness=0)
    st.map("TButton", background=[("active", BORDER), ("disabled", BG2)],
           foreground=[("disabled", FG_DIM)])
    st.configure("Accent.TButton", background=ACCENT, foreground="white")
    st.map("Accent.TButton", background=[("active", ACCENT_ACTIVE), ("disabled", BG3)])
    st.configure("Small.TButton", padding=(6, 2), font=FONT_SMALL)

    st.configure("TEntry", fieldbackground=BG_INPUT, foreground=FG, insertcolor=FG, borderwidth=1)
    st.configure("TCombobox", fieldbackground=BG_INPUT, foreground=FG, background=BG_INPUT)
    st.map("TCombobox", fieldbackground=[("readonly", BG_INPUT)], foreground=[("readonly", FG)])
    st.configure("TCheckbutton", background=BG, foreground=FG)

    st.configure("TNotebook", background=BG, borderwidth=0)
    st.configure("TNotebook.Tab", background=BG2, foreground=FG_DIM, padding=(14, 6))
    st.map("TNotebook.Tab", background=[("selected", BG3)], foreground=[("selected", FG)])

    st.configure("Treeview", background=BG2, fieldbackground=BG2, foreground=FG,
                 rowheight=26, borderwidth=0)
    st.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "white")])
    st.configure("Treeview.Heading", background=BG3, foreground=FG_DIM, font=FONT_SMALL)

    st.configure("TProgressbar", background=BG3, troughcolor=BG3)
    st.configure("Accent.Horizontal.TProgressbar", background=ACCENT, troughcolor=BG3)
    st.configure("TScrollbar", background=BG2, troughcolor=BG)
