"""Pareamento entre a aba do terminal e a sessão de agente, sem adivinhação quando possível.

1. Hook SessionStart do Claude Code: o script lê VULCAN_SESSION_ID (herdado da aba) e grava
   <dados>/pairings/<sessão>.json. Só é instalado por `--instalar-hook`, com backup do settings.json.
2. Reserva sem hook (e para o Codex): mesma pasta e início até 60 s depois de a aba abrir ou de `claude`/`codex`
   ser digitado nela. Subagente e app desktop não nascem de uma aba e ficam de fora. Na disputa, os pares seguem a
   ordem no tempo: o maior número possível e, no empate, os menores intervalos.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import time
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from vulcan_celox.core.agents import attention_hook
from vulcan_celox.core.agents.model import AgentSession, epoch

WINDOW_SECONDS = 60
SCRIPT_NAME = "vulcan-pareamento.py"
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
_AGENT_COMMAND = {"claude": re.compile(r"^\s*(?:\S*/)?claude(?:\s|$)"), "codex": re.compile(r"^\s*(?:\S*/)?codex(?:\s|$)")}

HOOK_SCRIPT = '''#!/usr/bin/env python3
"""Hook SessionStart do Claude Code instalado pelo Vulcan Celox (--instalar-hook).

Grava qual aba do Vulcan Celox abriu esta sessão. Fora de uma aba do Vulcan, não faz nada.
Nunca falha: qualquer problema termina com código 0 para não atrapalhar o Claude Code.
"""
import json, os, re, sys, tempfile

PAIRINGS = {pairings!r}

def main():
    tab = os.environ.get("VULCAN_SESSION_ID", "")
    if not re.match(r"^[A-Za-z0-9._-]{{1,120}}$", tab):
        return
    try:
        data = json.loads(sys.stdin.read() or "{{}}")
    except ValueError:
        return
    sid = data.get("session_id") if isinstance(data, dict) else None
    if not isinstance(sid, str) or not re.match(r"^[A-Za-z0-9._-]{{1,120}}$", sid):
        return
    os.makedirs(PAIRINGS, exist_ok=True)
    record = {{"session_id": sid, "terminal_id": tab, "theme": os.environ.get("VULCAN_THEME") or None,
              "cwd": data.get("cwd"), "source": data.get("source")}}
    fd, tmp = tempfile.mkstemp(dir=PAIRINGS, suffix=".tmp")
    with os.fdopen(fd, "w") as fh:
        json.dump(record, fh)
    os.replace(tmp, os.path.join(PAIRINGS, sid + ".json"))

try:
    main()
except Exception:
    pass
sys.exit(0)
'''


def pairings_dir(data_dir) -> Path:
    return Path(data_dir) / "pairings"


def read_pairings(folder) -> Dict[str, Dict[str, Optional[str]]]:
    """{sessão de agente: {terminal_id, theme}} a partir dos arquivos gravados pelo hook."""
    out: Dict[str, Dict[str, Optional[str]]] = {}
    folder = Path(folder)
    if not folder.is_dir():
        return out
    for path in folder.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get("session_id"), str) and isinstance(data.get("terminal_id"), str):
            theme = data.get("theme")
            out[data["session_id"]] = {"terminal_id": data["terminal_id"], "theme": theme if isinstance(theme, str) else None}
    return out


def _same_folder(agent_cwd: str, root: str, tab_cwd: str) -> bool:
    tab_cwd = (tab_cwd or "").rstrip("/")
    return bool(tab_cwd) and tab_cwd in ((agent_cwd or "").rstrip("/"), (root or "").rstrip("/"))


def _launches(tab, agent: str) -> List[float]:
    """Momentos em que o agente pode ter nascido nesta aba. Abrir a aba e digitar o comando logo depois é um só."""
    pattern = _AGENT_COMMAND.get(agent)
    typed = [epoch(c.get("ts")) for c in tab.commands if pattern and pattern.match(c.get("cmd", ""))]
    typed = [t for t in typed if t is not None]
    created = epoch(tab.created_at)
    if created is not None and not any(0 <= t - created <= WINDOW_SECONDS for t in typed):
        typed.append(created)
    return typed


def _match(starts: Sequence[float], launches: Sequence[float]) -> List[Tuple[int, int]]:
    """Pares (sessão, lançamento) em ordem no tempo, listas já ordenadas: mais pares e, no empate, menores intervalos."""
    n, m = len(starts), len(launches)
    # melhor[i][j]: (pares, -soma dos intervalos) usando starts[i:] e launches[j:]
    best = [[(0, 0.0)] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            options = [best[i + 1][j], best[i][j + 1]]
            gap = starts[i] - launches[j]
            if 0 <= gap <= WINDOW_SECONDS:
                rest = best[i + 1][j + 1]
                options.append((rest[0] + 1, rest[1] - gap))
            best[i][j] = max(options)
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        gap = starts[i] - launches[j]
        rest = best[i + 1][j + 1]
        if 0 <= gap <= WINDOW_SECONDS and best[i][j] == (rest[0] + 1, rest[1] - gap):
            pairs.append((i, j))
            i, j = i + 1, j + 1
        elif best[i][j] == best[i + 1][j]:
            i += 1
        else:
            j += 1
    return pairs


def resolve(agents: Sequence[AgentSession], tabs: Sequence, files: Mapping[str, Dict]) -> Dict[str, Dict]:
    """{sessão de agente: {terminal_id, theme, how}}. O arquivo do hook vence; senão pasta e horário."""
    by_tab = {t.id: t for t in tabs}
    out: Dict[str, Dict] = {}
    waiting: List[Tuple[float, AgentSession]] = []
    for s in agents:
        hooked = files.get(s.id)
        if hooked:
            tab = by_tab.get(hooked["terminal_id"])
            theme = hooked.get("theme") or (tab.theme if tab else None)
            out[s.id] = {"terminal_id": hooked["terminal_id"], "theme": theme, "how": "hook"}
            continue
        start = epoch(s.started_at)
        if start is not None and not s.origin:
            waiting.append((start, s))
    # a disputa é por agente e pela pasta da aba: abas de pastas diferentes não competem entre si
    folders = sorted({(t.cwd or "").rstrip("/") for t in tabs})
    for kind in sorted({s.agent for _, s in waiting}):
        for folder in folders:
            launches = sorted(((at, t.id) for t in tabs if (t.cwd or "").rstrip("/") == folder
                               for at in _launches(t, kind)), key=lambda x: (x[0], x[1]))
            if not launches:
                continue
            times = [at for at, _ in launches]
            # só quem tem algum lançamento na janela entra na conta: o histórico inteiro não precisa
            rivals = sorted(((start, s.id, s) for start, s in waiting
                             if s.agent == kind and s.id not in out and _same_folder(s.cwd, s.project_root, folder)
                             and any(0 <= start - at <= WINDOW_SECONDS for at in times)), key=lambda x: (x[0], x[1]))
            for i, j in _match([r[0] for r in rivals], times):
                session, tab = rivals[i][2], by_tab[launches[j][1]]
                out[session.id] = {"terminal_id": tab.id, "theme": tab.theme, "how": "pasta e horário"}
    return out


def apply(sessions: List[AgentSession], pairs: Mapping[str, Dict]) -> List[AgentSession]:
    for s in sessions:
        pair = pairs.get(s.id)
        if pair:
            s.pairing_id, s.theme = pair["terminal_id"], pair.get("theme")
    return sessions


# ── instalação do hook (só por --instalar-hook) ─────────────────────────────
def install_hook(claude_root, data_dir, now: Optional[float] = None) -> Dict[str, Optional[str]]:
    """Grava o script na pasta de dados do app e acrescenta o hook ao settings.json do Claude, com backup.
    Idempotente: rodar de novo não duplica a entrada. É a única escrita do app em ~/.claude."""
    claude_root, data_dir = Path(claude_root), Path(data_dir)
    script = data_dir / "hooks" / SCRIPT_NAME
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(HOOK_SCRIPT.format(pairings=str(pairings_dir(data_dir))), encoding="utf-8")
    script.chmod(0o755)
    settings_path = claude_root / "settings.json"
    backup: Optional[Path] = None
    settings: Dict = {}
    if settings_path.is_file():
        raw = settings_path.read_text(encoding="utf-8")
        settings = json.loads(raw) if raw.strip() else {}
        if not isinstance(settings, dict):
            raise ValueError("settings.json do Claude não é um objeto JSON")
        backup = settings_path.with_name(f"settings.json.vulcan-backup-{int(now if now is not None else time.time())}")
        backup.write_text(raw, encoding="utf-8")
    attention_ready = attention_hook.install(settings, data_dir)
    hooks = settings.setdefault("hooks", {})
    entries = hooks.setdefault("SessionStart", [])
    # o Claude Code roda o comando pelo shell: sem aspas, "Application Support" quebra o caminho
    command = shlex.quote(str(script))
    ours = (command, str(script))  # a entrada sem aspas gravada até a 0.3.0 é trocada, não duplicada
    present = False
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for hook in entry.get("hooks", []):
            if isinstance(hook, dict) and hook.get("command") in ours:
                hook["command"] = command
                present = True
    if not present:
        entries.append({"hooks": [{"type": "command", "command": command}]})
    claude_root.mkdir(parents=True, exist_ok=True)
    tmp = settings_path.with_name(".settings.json.vulcan-tmp")
    tmp.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, settings_path)
    return {"script": command, "settings": str(settings_path), "backup": str(backup) if backup else None,
            "already_installed": present and attention_ready}
