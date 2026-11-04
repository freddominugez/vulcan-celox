"""Order of the sites in the sidebar: favorites on top, the rest in alphabetical order."""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple


def matches(site, query: str) -> bool:
    q = (query or "").strip().lower()
    return not q or q in site.name.lower() or q in site.domain.lower()


def arrange_sidebar(sites: Iterable, favorites: Sequence[str], query: str = "") -> List[Tuple[str, list]]:
    """[(title, sites)]: "Favoritos" (if any) and "Sites", without repeats, filtered by name or domain."""
    wanted = set(favorites)
    shown = sorted((s for s in sites if matches(s, query)), key=lambda s: s.name.lower())
    fav = [s for s in shown if s.name in wanted]
    rest = [s for s in shown if s.name not in wanted]
    return [(title, items) for title, items in (("Favoritos", fav), ("Sites", rest)) if items]
