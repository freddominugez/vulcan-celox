"""Modelo normalizado das sessões de agente, igual para Claude Code e Codex (docs/en/agent-file-formats.md, seção 3)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

AGENTS = ("claude", "codex")
PUBLISH_STATES = ("none", "committed", "pushed", "pr_open")
FILE_KINDS = ("edit", "new", "read", "delete")
COMMAND_KINDS = ("shell", "test", "publish")
EVENT_KINDS = ("user", "assistant", "command", "file")
MAX_COMMANDS = 200
_FRACTION = re.compile(r"\.(\d+)")


# ── conversões seguras: os JSONL são de terceiros e o formato muda sem aviso ──
def parse_iso(value: Any) -> Optional[datetime]:
    """ISO 8601 para datetime com fuso. Aceita Z e frações de qualquer tamanho (o Python 3.9 só aceita 3 ou 6)."""
    if not isinstance(value, str) or not value:
        return None
    text = _FRACTION.sub(lambda m: "." + (m.group(1) + "000000")[:6], value.strip().replace("Z", "+00:00"), count=1)
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def epoch(value: Any) -> Optional[float]:
    dt = parse_iso(value)
    return dt.timestamp() if dt else None


def local_day(value: Any) -> Optional[str]:
    """Dia (AAAA-MM-DD) no fuso desta máquina."""
    dt = parse_iso(value)
    return dt.astimezone().date().isoformat() if dt else None


def as_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


def as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


@dataclass
class FileTouch:
    path: str
    kind: str
    first_at: str = ""
    last_at: str = ""


@dataclass
class CommandRun:
    text: str
    at: str = ""
    kind: str = "shell"
    exit_code: Optional[int] = None


@dataclass
class SessionEvent:
    at: str
    kind: str
    text: str
    tool: Optional[str] = None


@dataclass
class AgentSession:
    id: str
    agent: str
    file_path: str
    cwd: str = ""
    project_name: str = ""
    project_root: str = ""
    git_branch: Optional[str] = None
    worktree: Optional[str] = None
    title: Optional[str] = None
    started_at: str = ""
    last_activity_at: str = ""
    is_active: bool = False
    model: Optional[str] = None
    cli_version: Optional[str] = None
    turns: int = 0
    files: List[FileTouch] = field(default_factory=list)
    commands: List[CommandRun] = field(default_factory=list)
    commands_total: int = 0
    published: str = "none"
    pr_opened: bool = False
    tokens: Optional[Dict[str, int]] = None
    first_user_message: Optional[str] = None
    subagents: int = 0
    origin: str = ""  # Subagent ou desktop quando a sessão não nasce de uma aba; vazio nos outros casos
    pairing_id: Optional[str] = None
    theme: Optional[str] = None
    loop_alert: Optional[Dict] = None
    parse_errors: int = 0
    # contagens guardadas no resumo leve (a lista usa estas; files e commands só vêm no detalhe)
    files_count: int = 0
    edited_count: int = 0

    def edited_files(self) -> List[FileTouch]:
        return [f for f in self.files if f.kind != "read"]

    def edited_total(self) -> int:
        return len(self.edited_files()) if self.files else self.edited_count

    def files_total(self) -> int:
        return len(self.files) if self.files else self.files_count

    def light_dict(self) -> Dict:
        """Resumo sem as listas de arquivos e comandos, que ficam nas tabelas próprias do índice."""
        data = asdict(self)
        data["files_count"], data["edited_count"] = len(self.files), len(self.edited_files())
        data["files"], data["commands"] = [], []
        return data

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "AgentSession":
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in (data or {}).items() if k in known}
        clean["files"] = [FileTouch(**f) for f in clean.get("files") or [] if isinstance(f, dict)]
        clean["commands"] = [CommandRun(**c) for c in clean.get("commands") or [] if isinstance(c, dict)]
        return cls(**clean)
