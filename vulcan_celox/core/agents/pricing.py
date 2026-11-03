"""Preço por milhão de tokens de cada modelo e custo estimado de um turno.

Os valores padrão foram conferidos nas páginas oficiais em CONFERIDO_EM (ver FONTES). O usuário pode
sobrescrever qualquer modelo em <dados>/precos.json; o arquivo dele vence o padrão, modelo por modelo.
Modelo sem preço fica sem custo (None, nunca 0). Nenhuma consulta de rede: só o que está aqui e no arquivo.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

FILE_NAME = "precos.json"
CURRENCY = "USD"
CONFERIDO_EM = "2026-11-01"
FONTES = {
    "anthropic": "https://platform.claude.com/docs/en/about-claude/pricing",
    "openai": "https://developers.openai.com/api/docs/pricing",
}
KINDS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")
MAX_FILE = 256 * 1024
_DATE_SUFFIX = re.compile(r"-(\d{8}|\d{4}-\d{2}-\d{2})$")


def _p(i, o, r, w5, w1, fonte, acima=None) -> Dict:
    out = {"input": i, "output": o, "cache_read": r, "cache_write_5m": w5, "cache_write_1h": w1, "fonte": fonte}
    if acima:
        out["acima"] = acima
    return out


def _lc(tokens, i, o, r, w5, w1) -> Dict:
    """Preço de contexto longo: vale quando o prompt do turno passa de `tokens`."""
    return {"tokens": tokens, "input": i, "output": o, "cache_read": r, "cache_write_5m": w5, "cache_write_1h": w1}


A, O = "anthropic", "openai"
# Anthropic: entrada, saída, leitura de cache, escrita de cache 5 min e 1 h.
# OpenAI: entrada, saída, entrada em cache, escrita de cache 30 min (vai na coluna 5m) e 12 h (coluna 1h);
# "-" na página vira None: turno que usou esse tipo de token fica sem custo.
DEFAULT: Dict[str, Dict] = {
    "claude-fable-5-1": _p(10, 50, 0.25, 12.5, 20, A),
    "claude-fable-5": _p(10, 50, 1, 12.5, 20, A),
    "claude-mythos-5-1": _p(10, 50, 0.25, 12.5, 20, A),
    "claude-mythos-5": _p(10, 50, 1, 12.5, 20, A),
    "claude-opus-5-5": _p(4, 20, 0.20, 5, 8, A),
    "claude-opus-5": _p(5, 25, 0.50, 6.25, 10, A),
    "claude-opus-4-8": _p(5, 25, 0.50, 6.25, 10, A),
    "claude-opus-4-7": _p(5, 25, 0.50, 6.25, 10, A),
    "claude-opus-4-6": _p(5, 25, 0.50, 6.25, 10, A),
    "claude-opus-4-5": _p(5, 25, 0.50, 6.25, 10, A),
    "claude-opus-4-1": _p(15, 75, 1.50, 18.75, 30, A),
    "claude-opus-4": _p(15, 75, 1.50, 18.75, 30, A),
    "claude-sonnet-5-5": _p(2, 10, 0.10, 2.5, 4, A),
    "claude-sonnet-5": _p(2, 10, 0.20, 2.5, 4, A),
    "claude-sonnet-4-6": _p(3, 15, 0.30, 3.75, 6, A),
    "claude-sonnet-4-5": _p(3, 15, 0.30, 3.75, 6, A),
    "claude-sonnet-4": _p(3, 15, 0.30, 3.75, 6, A),
    "claude-haiku-5-5": _p(0.10, 0.50, 0.01, 0.125, 0.20, A, _lc(100000, 0.50, 2.50, 0.05, 0.625, 1)),
    "claude-haiku-4-5": _p(1, 5, 0.10, 1.25, 2, A),
    "claude-3-5-haiku": _p(0.80, 4, 0.08, 1, 1.6, A),
    "gpt-6-astra": _p(10, 50, 1, 12.5, 25, O, _lc(272000, 20, 75, 2, 25, 50)),
    "gpt-6.1-sol": _p(2, 10, 0.10, 2.5, 5, O, _lc(272000, 4, 15, 0.20, 5, 10)),
    "gpt-6.1-terra": _p(1, 5, 0.05, 1.25, 2.5, O, _lc(272000, 2, 7.5, 0.10, 2.5, 5)),
    "gpt-6-sol": _p(2, 10, 0.20, 2.5, 5, O, _lc(272000, 4, 15, 0.40, 5, 10)),
    "gpt-6-luna": _p(0.10, 0.50, 0.01, 0.125, 0.25, O, _lc(272000, 0.20, 0.75, 0.02, 0.25, 0.50)),
    "gpt-5.6-sol": _p(4, 20, 0.40, 5, 10, O, _lc(272000, 8, 30, 0.80, 10, 20)),
    "gpt-5.6-terra": _p(2, 12, 0.20, 2.5, 5, O, _lc(272000, 4, 18, 0.40, 5, 10)),
    "gpt-5.6-luna": _p(0.20, 1.20, 0.02, 0.25, 0.50, O, _lc(272000, 0.40, 1.80, 0.04, 0.50, 1)),
    "gpt-5.5": _p(5, 30, 0.50, None, None, O, _lc(272000, 10, 45, 1, None, None)),
    "gpt-5.4": _p(2.5, 15, 0.25, None, None, O, _lc(272000, 5, 22.5, 0.50, None, None)),
    "gpt-5.3-codex": _p(1.75, 14, 0.175, None, None, O),
    "gpt-5.2": _p(1.75, 14, 0.175, None, None, O),
    "gpt-5.1": _p(1.25, 10, 0.125, None, None, O),
    "gpt-5": _p(1.25, 10, 0.125, None, None, O),
    "gpt-5-mini": _p(0.25, 2, 0.025, None, None, O),
}


def prices_path(data_dir) -> Path:
    return Path(data_dir) / FILE_NAME


def normalize(model: str) -> str:
    """Nome do modelo sem a data de versão nem sufixo de variante: claude-opus-5-5-20261001 -> claude-opus-5-5."""
    name = (model or "").strip().lower()
    name = name.split("[", 1)[0].split("@", 1)[0]
    return _DATE_SUFFIX.sub("", name)


def _valid_entry(entry) -> bool:
    if not isinstance(entry, dict):
        return False
    for k in KINDS:
        v = entry.get(k)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0):
            return False
    acima = entry.get("acima")
    return acima is None or (isinstance(acima, dict) and isinstance(acima.get("tokens"), int) and _valid_entry(
        {k: acima.get(k) for k in KINDS}))


def load(data_dir) -> Tuple[Dict[str, Dict], Optional[str]]:
    """Tabela efetiva (padrão + arquivo do usuário) e o aviso para o --doctor, se o arquivo não valeu."""
    table = {k: dict(v) for k, v in DEFAULT.items()}
    path = prices_path(data_dir)
    if not path.exists():
        return table, None
    try:
        if path.stat().st_size > MAX_FILE:
            raise ValueError(f"maior que {MAX_FILE // 1024} KB")
        data = json.loads(path.read_text(encoding="utf-8"))
        models = data.get("modelos") if isinstance(data, dict) else None
        if not isinstance(models, dict):
            raise ValueError('falta o objeto "modelos"')
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        return table, f"{path}: JSON inválido ({exc}); valem os preços padrão"
    bad = []
    for name, entry in models.items():
        if _valid_entry(entry):
            table[normalize(name)] = {**entry, "fonte": entry.get("fonte") or "usuário"}
        else:
            bad.append(str(name))
    return table, (f"{path}: preço inválido para {', '.join(sorted(bad))}; esses modelos ficam no padrão"
                   if bad else None)


def lookup(table: Dict[str, Dict], model: str) -> Optional[Dict]:
    return table.get(normalize(model))


def cost(row: Dict, table: Dict[str, Dict]) -> Optional[float]:
    """Custo em USD de uma linha de uso, ou None se o modelo (ou um tipo de token usado) não tem preço."""
    entry = lookup(table, row.get("model") or "")
    if entry is None:
        return None
    prompt = sum(int(row.get(k) or 0) for k in ("input", "cache_read", "cache_write_5m", "cache_write_1h"))
    acima = entry.get("acima")
    if isinstance(acima, dict) and prompt > int(acima.get("tokens") or 0):
        entry = acima
    total = 0.0
    for k in KINDS:
        n = int(row.get(k) or 0)
        if not n:
            continue
        price = entry.get(k)
        if price is None:
            return None
        total += n * float(price) / 1_000_000
    return total


def describe(data_dir) -> Dict:
    """Resumo para o --doctor: arquivo, moeda, data e fonte dos padrões, quantos modelos e o aviso."""
    table, warning = load(data_dir)
    return {"arquivo": str(prices_path(data_dir)), "existe": prices_path(data_dir).exists(), "moeda": CURRENCY,
            "conferido_em": CONFERIDO_EM, "fontes": FONTES, "modelos": len(table), "aviso": warning}
