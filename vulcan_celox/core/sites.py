"""Site discovery: Valet's parked and linked plus the app's manual sites."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional

KIND_PRIORITY = {"lerd": 4, "linked": 3, "parked": 2, "manual": 1}
KIND_ORDER = ("lerd", "linked", "parked", "manual")
DEFAULT_TLD = "test"


@dataclass(frozen=True)
class Site:
    name: str
    domain: str
    path: str
    kind: str  # lerd | parked | linked | manual
    tld: str = DEFAULT_TLD
    secured: bool = False
    php: str = ""
    node: str = ""

    @property
    def url(self) -> str:
        return f"{'https' if self.secured else 'http'}://{self.domain}"


def normalize_name(name: str) -> str:
    return name[4:] if name.lower().startswith("www.") else name


def read_valet_config(valet_home: Optional[Path]) -> Dict:
    if valet_home is None:
        return {}
    try:
        with open(Path(valet_home) / "config.json", "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def discover_sites(valet_home: Optional[Path], manual: Optional[Mapping[str, str]] = None) -> List[Site]:
    """Merges parked (subfolders of config.paths), linked (symlinks in Sites/) and manual.

        Dedupe by domain with priority linked > parked > manual. Nonexistent
        paths, hidden folders and broken symlinks are ignored.
    """
    config = read_valet_config(valet_home)
    tld = str(config.get("tld") or DEFAULT_TLD)
    found: Dict[str, Site] = {}

    def add(raw_name: str, path: Path, kind: str) -> None:
        name = normalize_name(raw_name)
        if not name:
            return
        domain = f"{name.lower()}.{tld}"
        site = Site(name=name, domain=domain, path=str(path), kind=kind, tld=tld)
        current = found.get(domain)
        if current is None or KIND_PRIORITY[kind] > KIND_PRIORITY[current.kind]:
            found[domain] = site

    for parked in config.get("paths") or []:
        if not isinstance(parked, str):
            continue
        root = Path(parked).expanduser()
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if child.name.startswith(".") or not child.is_dir():
                continue
            add(child.name, child.resolve(), "parked")

    if valet_home is not None:
        links = Path(valet_home) / "Sites"
        if links.is_dir():
            for child in sorted(links.iterdir()):
                if child.name.startswith(".") or not child.is_symlink():
                    continue
                target = child.resolve()
                if target.is_dir():
                    add(child.name, target, "linked")

    for name, path in (manual or {}).items():
        if isinstance(name, str) and isinstance(path, str) and Path(path).expanduser().is_dir():
            add(name, Path(path).expanduser(), "manual")

    return sorted(found.values(), key=lambda s: (KIND_ORDER.index(s.kind), s.name.lower()))
