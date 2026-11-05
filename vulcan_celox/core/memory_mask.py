"""Masks the memory files saved before the mask existed. There is no way back, so it only runs when the user asks."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from vulcan_celox.core.redact import masked_count, redact
from vulcan_celox.core.session_memory import SESSIONS_DIR
from vulcan_celox.core.store import write_text_atomic


def mask_saved_memories(data_dir) -> Tuple[int, int]:
    """Returns (files changed, secrets masked)."""
    files = secrets = 0
    for path in sorted((Path(data_dir) / SESSIONS_DIR).rglob("*.md")):
        if path.is_symlink() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        masked, _ = redact(text)
        if masked != text:
            write_text_atomic(path, masked)
            files += 1
            secrets += max(0, masked_count(masked) - masked_count(text))
    return files, secrets
