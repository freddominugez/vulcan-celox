"""Idioma: inglês por padrão, português disponível. O texto-fonte é o português; o dicionário é web/i18n/en.json, o mesmo da
interface. `tr()` traduz texto do servidor; chave com {nome} também casa com o texto já preenchido."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Pattern, Tuple

LANGUAGES = ("en", "pt")
DEFAULT = "en"
FILE = Path(__file__).resolve().parent.parent / "web" / "i18n" / "en.json"

_language = os.environ.get("VULCAN_LANGUAGE") if os.environ.get("VULCAN_LANGUAGE") in LANGUAGES else DEFAULT
_dictionary: Optional[Dict[str, str]] = None
_patterns: List[Tuple[Pattern, str]] = []


def dictionary() -> Dict[str, str]:
    global _dictionary, _patterns
    if _dictionary is None:
        _dictionary = json.loads(FILE.read_text(encoding="utf-8"))
        _patterns = []
        for key, value in _dictionary.items():
            if "{" in key:
                regex = re.sub(r"\\\{(\w+)\\\}", r"(?P<\1>.+?)", re.escape(key))
                _patterns.append((re.compile("^" + regex + "$", re.S), value))
    return _dictionary


def set_language(language: str) -> None:
    global _language
    _language = language if language in LANGUAGES else DEFAULT


def language() -> str:
    return _language


def resolve(prefs: Mapping, env: Mapping[str, str]) -> str:
    """VULCAN_LANGUAGE manda (sensores e testes); depois a preferência."""
    chosen = env.get("VULCAN_LANGUAGE") or prefs.get("language") or DEFAULT
    return chosen if chosen in LANGUAGES else DEFAULT


def tr(text: str, **values) -> str:
    """Texto na língua atual. Com valores, preenche {nome}; sem valores, reconhece também texto já preenchido."""
    if _language == "pt":
        return text.format(**values) if values else text
    table = dictionary()
    if values:
        return table.get(text, text).format(**values)
    if text in table:
        return table[text]
    for pattern, value in _patterns:
        match = pattern.match(text)
        if match:
            return value.format(**match.groupdict())
    return text
