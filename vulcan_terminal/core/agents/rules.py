"""Heurísticas como dados: ferramenta para efeito, o que é teste, o que é publicação, onde fica a worktree.

Adicionar uma ferramenta ou um comando de teste é uma linha nas tabelas abaixo, não um `if` nos leitores.
"""

from __future__ import annotations

import os
import re
from typing import Callable, Dict, List, Optional, Tuple

# efeito: ("file", caminho, tipo) ou ("command", texto); tipo "write" vira "new" ou "edit" no montador
Effect = Tuple[str, ...]


def _file(field_name: str, kind: str) -> Callable[[dict], List[Effect]]:
    def extract(data: dict) -> List[Effect]:
        path = data.get(field_name) if isinstance(data, dict) else None
        return [("file", path, kind)] if isinstance(path, str) and path else []
    return extract


def _command(field_name: str) -> Callable[[dict], List[Effect]]:
    def extract(data: dict) -> List[Effect]:
        text = data.get(field_name) if isinstance(data, dict) else None
        return [("command", text)] if isinstance(text, str) and text.strip() else []
    return extract


CLAUDE_TOOLS: Dict[str, Callable[[dict], List[Effect]]] = {
    "Edit": _file("file_path", "edit"),
    "MultiEdit": _file("file_path", "edit"),
    "NotebookEdit": _file("notebook_path", "edit"),
    "Write": _file("file_path", "write"),
    "Read": _file("file_path", "read"),
    "NotebookRead": _file("notebook_path", "read"),
    "Bash": _command("command"),
}


def claude_tool_effects(name: str, data: dict) -> List[Effect]:
    extract = CLAUDE_TOOLS.get(name)
    return extract(data) if extract else []


# ── apply_patch do Codex ────────────────────────────────────────────────────
PATCH_LINE = re.compile(r"^\*\*\* (Add|Update|Delete) File: (.+?)\s*$|^\*\*\* Move to: (.+?)\s*$", re.M)
PATCH_KINDS = {"Add": "new", "Update": "edit", "Delete": "delete"}
CODEX_CHANGE_KINDS = {"add": "new", "update": "edit", "delete": "delete"}


def patch_effects(text: str) -> List[Effect]:
    out: List[Effect] = []
    for match in PATCH_LINE.finditer(text or ""):
        if match.group(3):
            out.append(("file", match.group(3), "new"))
        else:
            out.append(("file", match.group(2), PATCH_KINDS[match.group(1)]))
    return out


# ── comandos ────────────────────────────────────────────────────────────────
TEST_PATTERNS = [re.compile(p) for p in (
    r"\bpytest\b", r"\bphpunit\b", r"\bartisan\s+test\b", r"\bpest\b", r"-m\s+unittest\b",
    r"\b(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?test\b", r"\bvitest\b", r"\bjest\b", r"\bgo\s+test\b",
    r"\bcargo\s+test\b", r"\bmake\s+test\b", r"\brspec\b", r"\bvalidate\.sh\b", r"\btest_linux\.sh\b",
)]
_GIT = r"\bgit\s+(?:-C\s+\S+\s+|-c\s+\S+\s+)*"
# do mais alto para o mais baixo; o primeiro que casar vale
PUBLISH_PATTERNS = (
    ("pr_open", re.compile(r"\bgh\s+pr\s+create\b")),
    ("pushed", re.compile(_GIT + r"push\b")),
    ("committed", re.compile(_GIT + r"commit\b")),
)
_SEGMENTS = re.compile(r"\s*(?:&&|\|\||;|\|)\s*")


def publish_level(text: str) -> Optional[str]:
    for level, pattern in PUBLISH_PATTERNS:
        if pattern.search(text or ""):
            return level
    return None


def publish_sequence(text: str) -> List[str]:
    """Níveis de publicação na ordem dos trechos: `git commit && git push` dá [committed, pushed]."""
    return [level for level in (publish_level(seg) for seg in _SEGMENTS.split(text or "")) if level]


def is_test(text: str) -> bool:
    return any(p.search(text or "") for p in TEST_PATTERNS)


def classify_command(text: str) -> str:
    if publish_level(text):
        return "publish"
    return "test" if is_test(text) else "shell"


def test_key(text: str) -> Optional[str]:
    """O trecho que roda o teste, sem `cd ... &&` antes nem `| tail` depois: mesma chave = mesmo teste."""
    for segment in _SEGMENTS.split(text or ""):
        if is_test(segment):
            return " ".join(segment.split())
    return None


# ── projeto e worktree ──────────────────────────────────────────────────────
WORKTREE = re.compile(r"^(?P<root>.+?)/\.(?:claude|codex)/worktrees/(?P<name>[^/]+)")


def split_worktree(cwd: str) -> Tuple[str, Optional[str]]:
    """(raiz do repositório, nome da worktree ou None)."""
    match = WORKTREE.match(cwd or "")
    if match:
        return match.group("root"), match.group("name")
    return cwd or "", None


def worktree_path(cwd: str) -> Optional[str]:
    """Raiz da worktree que contém o cwd (`.../.claude/worktrees/<nome>`), mesmo se o cwd for uma subpasta."""
    match = WORKTREE.match(cwd or "")
    return match.group(0) if match else None


def project_name(cwd: str) -> str:
    root, _ = split_worktree(cwd)
    return os.path.basename(root.rstrip("/")) or root
