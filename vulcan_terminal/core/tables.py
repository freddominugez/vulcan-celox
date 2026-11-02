"""Parser das tabelas ASCII impressas pela CLI do Valet (formato Symfony Console)."""

from __future__ import annotations

from typing import Dict, List


def _is_border(line: str) -> bool:
    s = line.strip()
    return len(s) >= 2 and s[0] == "+" and s[-1] == "+" and set(s) <= set("+-=")


def _is_row(line: str) -> bool:
    s = line.strip()
    return len(s) >= 2 and s[0] == "|" and s[-1] == "|"


def _cells(line: str) -> List[str]:
    return [c.strip() for c in line.strip()[1:-1].split("|")]


def parse_table(text: str) -> List[Dict[str, str]]:
    """Converte a primeira tabela encontrada no texto em lista de dicts.

    Ignora texto antes e depois da tabela. Tabela só com cabeçalho retorna [].
    Linhas com número de células diferente do cabeçalho são completadas ou truncadas.
    """
    lines = text.splitlines()
    i = 0
    while i < len(lines) and not _is_border(lines[i]):
        i += 1
    # cabeçalho: primeira linha de dados depois da borda inicial
    while i < len(lines) and not _is_row(lines[i]):
        if not _is_border(lines[i]):
            return []
        i += 1
    if i >= len(lines):
        return []
    header = _cells(lines[i])
    rows: List[Dict[str, str]] = []
    i += 1
    while i < len(lines):
        line = lines[i]
        if _is_border(line):
            i += 1
            continue
        if not _is_row(line):
            break
        cells = _cells(line)
        cells = (cells + [""] * len(header))[:len(header)]
        rows.append(dict(zip(header, cells)))
        i += 1
    return rows
