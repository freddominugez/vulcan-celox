"""Offline product locales shared by Python, the web interface and the native shell."""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, Mapping, Optional

FOLDER = Path(__file__).resolve().parent.parent / "web" / "i18n"
LANGUAGE_INFO = tuple(json.loads((FOLDER / "languages.json").read_text(encoding="utf-8")))
LANGUAGES = tuple(item["id"] for item in LANGUAGE_INFO)
DEFAULT = "en"
FILE = FOLDER / "en.json"
MIN_LITERAL = 4


def normalize(value) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = value.strip().replace("_", "-").lower()
    return next((item["id"] for item in LANGUAGE_INFO if value in item["aliases"]), None)


_language = normalize(os.environ.get("VULCAN_LANGUAGE")) or DEFAULT


@lru_cache(maxsize=3)
def _catalog(chosen: str) -> Dict[str, str]:
    if chosen == "pt":
        return {}
    return json.loads((FOLDER / (chosen + ".json")).read_text(encoding="utf-8"))


def dictionary(chosen: Optional[str] = None) -> Dict[str, str]:
    """Resolve before consulting the cache: changing the language cannot reuse another catalog."""
    return _catalog(normalize(chosen) or _language)


@lru_cache(maxsize=3)
def _patterns(chosen: str):
    out = []
    for key, value in dictionary(chosen).items():
        # A generic key like {from} a {to} must not rewrite user text or already-translated errors.
        if "{" in key and not (key.startswith("{") and len(re.findall(r"[^\W\d_]", re.sub(r"\{\w+\}", "", key))) < MIN_LITERAL):
            regex = re.sub(r"\\\{(\w+)\\\}", r"(?P<\1>.+?)", re.escape(key))
            out.append((re.compile("^" + regex + "$", re.S), value))
    return out


def set_language(value: str) -> None:
    global _language
    _language = normalize(value) or DEFAULT


def language() -> str:
    return _language


def resolve(prefs: Mapping, env: Mapping[str, str]) -> str:
    """Environment override, then saved preference; invalid values use the default."""
    prefs = prefs if isinstance(prefs, Mapping) else {}
    return normalize(env.get("VULCAN_LANGUAGE") or prefs.get("language")) or DEFAULT


def tr(text: str, **values) -> str:
    chosen = _language
    if chosen == "pt":
        return text.format(**values) if values else text
    table = dictionary(chosen)
    if values:
        return table.get(text, text).format(**values)
    if text in table:
        return table[text]
    for pattern, value in _patterns(chosen):
        match = pattern.match(text)
        if match:
            return value.format(**match.groupdict())
    return text
