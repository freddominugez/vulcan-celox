"""Optional Claude Code attention hook: records only the notice type and the time, never the message text.

`Notification` and `Stop` report right away what the JSONL only shows later. Without this hook, the state comes from reading
the file (`attention.py`). Installed together with the pairing hook, only via `--instalar-hook`.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Dict

SCRIPT_NAME = "vulcan-atencao.py"
EVENTS = ("Notification", "Stop")
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
_MAX_FILES = 500

HOOK_SCRIPT = '''#!/usr/bin/env python3
"""Hook Notification e Stop do Claude Code instalado pelo Vulcan (--instalar-hook).

Grava o tipo do aviso e a hora. Não guarda o texto e não usa a rede.
Nunca falha: qualquer problema termina com código 0 para não atrapalhar o Claude Code.
"""
import json, os, re, sys, tempfile, time

FOLDER = {folder!r}

def main():
    data = json.loads(sys.stdin.read() or "{{}}")
    sid = data.get("session_id") if isinstance(data, dict) else None
    if not isinstance(sid, str) or not re.match(r"^[A-Za-z0-9._-]{{1,120}}$", sid):
        return
    event = data.get("hook_event_name")
    if event == "Stop":
        kind = "your_turn"
    elif event == "Notification":
        hint = str(data.get("notification_type") or "") + " " + str(data.get("message") or "")
        kind = "waiting_permission" if "permission" in hint.lower() else "your_turn"
    else:
        return
    os.makedirs(FOLDER, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=FOLDER, suffix=".tmp")
    with os.fdopen(fd, "w") as fh:
        json.dump({{"session_id": sid, "kind": kind, "at": time.time()}}, fh)
    os.replace(tmp, os.path.join(FOLDER, sid + ".json"))

try:
    main()
except Exception:
    pass
sys.exit(0)
'''


def attention_dir(data_dir) -> Path:
    return Path(data_dir) / "attention"


def read_records(folder) -> Dict[str, Dict]:
    """session -> valid record. A strange file is ignored: the folder belongs to the app, but the content comes from a script."""
    out: Dict[str, Dict] = {}
    try:
        paths = sorted(Path(folder).glob("*.json"))[:_MAX_FILES]
    except OSError:
        return out
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or not _SAFE_ID.match(str(data.get("session_id") or "")):
            continue
        if data.get("kind") in ("your_turn", "waiting_permission") and isinstance(data.get("at"), (int, float)):
            out[data["session_id"]] = {"kind": data["kind"], "at": float(data["at"])}
    return out


def install(settings: Dict, data_dir) -> bool:
    """Writes the script and adds the two events to `settings`, without duplicating. Returns whether it was already complete."""
    script = Path(data_dir) / "hooks" / SCRIPT_NAME
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(HOOK_SCRIPT.format(folder=str(attention_dir(data_dir))), encoding="utf-8")
    script.chmod(0o755)
    command = shlex.quote(str(script))
    hooks = settings.setdefault("hooks", {})
    complete = True
    for event in EVENTS:
        entries = hooks.setdefault(event, [])
        found = any(isinstance(hook, dict) and hook.get("command") == command
                    for entry in entries if isinstance(entry, dict) for hook in entry.get("hooks", []))
        if not found:
            entries.append({"hooks": [{"type": "command", "command": command}]})
            complete = False
    return complete
