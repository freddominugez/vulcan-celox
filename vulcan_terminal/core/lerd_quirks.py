"""Contornos do app para defeitos do Lerd achados nas provas.

Cada entrada diz o defeito, o que o app faz no lugar e a versão do Lerd que corrige (None enquanto não sair). O
comportamento do app não muda com a versão: limpar pela API com o cabeçalho e ler os nomes reais dos
php.ini continuam certos depois da correção. A tabela serve para o --doctor dizer o que ainda é necessário.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Quirk:
    id: str
    defeito: str
    contorno: str
    corrigido_em: Optional[str] = None  # versão do Lerd com a correção; None enquanto não sair


QUIRKS: Tuple[Quirk, ...] = (
    Quirk("dump-clear-csrf",
          "`lerd dump clear` responde 403 no macOS: a CLI fala com o painel por TCP sem o cabeçalho X-Lerd-CSRF",
          "o app limpa pela API do painel com o cabeçalho"),
    Quirk("dump-status-addr",
          "`lerd dump status` mostra o socket unix mesmo quando o receptor escuta em tcp:127.0.0.1:9913 (macOS)",
          "o app lê o endereço só de /api/dumps/status"),
    Quirk("php-ini-names",
          "a documentação cita 98-lerd-user.ini e 95-lerd-shared.ini (nomes dentro do contêiner); no disco são "
          "98-user.ini e 95-shared.ini",
          "o app lê e grava pelos nomes do disco e aceita os da documentação"),
)


def version_tuple(version: Optional[str]) -> Optional[Tuple[int, int, int]]:
    match = re.match(r"\s*v?(\d+)\.(\d+)\.(\d+)", version or "")
    return tuple(int(x) for x in match.groups()) if match else None  # type: ignore[return-value]


def is_needed(quirk: Quirk, version: Optional[str]) -> bool:
    """Versão desconhecida ou anterior à correção: o contorno segue necessário."""
    current, fixed = version_tuple(version), version_tuple(quirk.corrigido_em)
    return fixed is None or current is None or current < fixed


def status(version: Optional[str], quirks: Tuple[Quirk, ...] = QUIRKS) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = [{"id": q.id, "defeito": q.defeito, "contorno": q.contorno,
                                   "corrigido_em": q.corrigido_em, "necessario": is_needed(q, version)}
                                  for q in quirks]
    return {"versao": version or "", "contornos": rows, "necessarios": sum(1 for r in rows if r["necessario"])}
