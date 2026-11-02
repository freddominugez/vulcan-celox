"""Mascara segredos antes de qualquer texto sair da máquina (documentação com IA)."""

from __future__ import annotations

import re
from typing import Callable, List, Pattern, Tuple, Union

MASK = "[segredo]"

_SECRET_WORDS = r"(?:PASSWORD|PASSWD|PASS|PWD|SECRET|TOKEN|API_?KEY|ACCESS_?KEY|PRIVATE_?KEY|APP_KEY|AUTH|CREDENTIALS?|DSN)"

# (padrão, substituição): a substituição preserva nomes de variáveis e prefixos úteis para entender o comando
_RULES: List[Tuple[Pattern[str], Union[str, Callable]]] = [
    (re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----", re.S),
     "[chave privada removida]"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{10,}"), MASK),
    (re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{20,}"), MASK),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}"), MASK),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"), MASK),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), MASK),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}"), MASK),
    (re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[0-9A-Za-z]{16,}"), MASK),
    (re.compile(r"\bsb_(?:secret|publishable)_[A-Za-z0-9_\-]{10,}"), MASK),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), MASK),
    (re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/\-]{12,}=*"), lambda m: m.group(1) + MASK),
    # usuário:senha@ em URLs (mysql://, postgres://, redis://, https://)
    (re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://[^\s:/@]+:)([^\s@/]+)@"), lambda m: f"{m.group(1)}{MASK}@"),
    # CHAVE=valor e chave: valor com palavra sensível no nome
    (re.compile(r"(?i)\b([A-Z0-9_.\-]*" + _SECRET_WORDS + r"[A-Z0-9_.\-]*)(\s*[=:]\s*)([\"']?)"
                r"(?!\[segredo\])(?!(?:Bearer|Basic)\b)(?!(?:\d+|true|false|null|none|\$\{?[A-Z_]+\}?)\3(?:\s|$))([^\s\"']{3,})\3"),
     lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{MASK}{m.group(3)}"),
    # --password=valor, --token valor
    (re.compile(r"(?i)(--(?:password|passwd|token|api-key|secret)(?:=|\s+))(?!\[segredo\])(\S+)"),
     lambda m: m.group(1) + MASK),
    # mysql -psenha
    (re.compile(r"(\bmysql(?:dump|admin)?\b[^\n]*?\s-p)(?!\[segredo\])([^\s\-]\S*)"), lambda m: m.group(1) + MASK),
]


def redact(text: str) -> Tuple[str, int]:
    """Devolve (texto mascarado, quantos segredos foram mascarados)."""
    total = 0
    for pattern, replacement in _RULES:
        text, count = pattern.subn(replacement, text)
        total += count
    return text, total
