"""Masks secrets before text is saved to a memory file or leaves the machine (AI documentation)."""

from __future__ import annotations

import re
from typing import Callable, List, Pattern, Tuple, Union

MASK = "[segredo]"  # the mark in Portuguese
MASK_EN = "[secret]"
MASKS = (MASK, MASK_EN)
KEY_MASK = "[chave privada removida]"
_DONE = r"\[(?:segredo|secret)\]"  # either spelling is already masked: masking again must leave it alone


def mask_mark() -> str:
    """The mark in the interface language. What was saved with the other spelling stays as it is, and still counts."""
    from vulcan_celox.core import i18n
    return MASK_EN if i18n.language() == "en" else MASK

_SECRET_WORDS = r"(?:PASSWORD|PASSWD|PASS|PWD|SECRET|TOKEN|API_?KEY|ACCESS_?KEY|PRIVATE_?KEY|APP_KEY|AUTH|CREDENTIALS?|DSN)"

# (pattern, replacement): the replacement preserves variable names and prefixes useful for understanding the command
_RULES: List[Tuple[Pattern[str], Union[str, Callable]]] = [
    (re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----", re.S),
     KEY_MASK),
    # cut in half by the size limit of the terminal history: only one of the two markers is left
    (re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----(?:\s*\n[A-Za-z0-9+/=]+)*"), KEY_MASK),
    (re.compile(r"(?:^[A-Za-z0-9+/=]{16,}\n)*^[^\n]*-----END [A-Z0-9 ]*PRIVATE KEY-----", re.M), KEY_MASK),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{10,}"), lambda _m: mask_mark()),
    (re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{20,}"), lambda _m: mask_mark()),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}"), lambda _m: mask_mark()),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"), lambda _m: mask_mark()),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), lambda _m: mask_mark()),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}"), lambda _m: mask_mark()),
    (re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[0-9A-Za-z]{16,}"), lambda _m: mask_mark()),
    (re.compile(r"\bsb_(?:secret|publishable)_[A-Za-z0-9_\-]{10,}"), lambda _m: mask_mark()),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), lambda _m: mask_mark()),
    (re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/\-]{12,}=*"), lambda m: m.group(1) + mask_mark()),
    # user:password@ in URLs (mysql://, postgres://, redis://, https://)
    (re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://[^\s:/@]+:)(?!" + _DONE + r"@)([^\s@/]+)@"), lambda m: f"{m.group(1)}{mask_mark()}@"),
    # KEY=value and key: value with a sensitive word in the name
    (re.compile(r"(?i)\b([A-Z0-9_.\-]*" + _SECRET_WORDS + r"[A-Z0-9_.\-]*)(\s*[=:]\s*)([\"']?)"
                r"(?!" + _DONE + r")(?!(?:Bearer|Basic)\b)(?!(?:\d+|true|false|null|none|\$\{?[A-Z_]+\}?)\3(?:\s|$))([^\s\"']{3,})\3"),
     lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{mask_mark()}{m.group(3)}"),
    # --password=valor, --token valor
    (re.compile(r"(?i)(--(?:password|passwd|token|api-key|secret)(?:=|\s+))(?!" + _DONE + r")(\S+)"),
     lambda m: m.group(1) + mask_mark()),
    # curl -u nome:senha, sshpass -p senha
    (re.compile(r"(\bcurl\b[^\n]*?\s(?:-u\s*|--user[=\s]+)[^\s:]+:)(?!" + _DONE + r")(\S+)"), lambda m: m.group(1) + mask_mark()),
    (re.compile(r"(\bsshpass\b[^\n]*?\s-p\s*)(?!" + _DONE + r")(\S+)"), lambda m: m.group(1) + mask_mark()),
    # mysql -psenha
    (re.compile(r"(\bmysql(?:dump|admin)?\b[^\n]*?\s-p)(?!" + _DONE + r")([^\s\-]\S*)"), lambda m: m.group(1) + mask_mark()),
]


def masked_count(text: str) -> int:
    """How many masks a text already holds. The session memory arrives masked, and the count must still be true."""
    return sum(text.count(mark) for mark in MASKS) + text.count(KEY_MASK)


def redact(text: str) -> Tuple[str, int]:
    """Devolve (texto mascarado, quantos segredos foram mascarados)."""
    total = 0
    for pattern, replacement in _RULES:
        text, count = pattern.subn(replacement, text)
        total += count
    return text, total
