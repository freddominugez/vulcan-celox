"""Reads a project file for the code viewer. Read-only; the content is always data."""

from __future__ import annotations

import fnmatch
import hashlib
import os
import stat
from pathlib import Path
from typing import Any, Dict, Iterable

MAX_BYTES = 1024 * 1024
SENSITIVE_NAMES = (".env*", "*.pem", "*.key", "id_rsa*", "credentials*")
SENSITIVE_DIRS = (".git", ".ssh", ".aws", ".gnupg")
LANGUAGES = {
    ".php": "php", ".phtml": "php", ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".jsx": "jsx",
    ".ts": "typescript", ".tsx": "tsx", ".py": "python", ".html": "html", ".htm": "html", ".vue": "html",
    ".css": "css", ".scss": "css", ".json": "json", ".md": "markdown", ".markdown": "markdown", ".sql": "sql",
    ".yml": "yaml", ".yaml": "yaml",
}


class CodeReadError(Exception):
    """Refusal with a reason the interface knows how to show."""

    def __init__(self, status: int, reason: str, message: str):
        super().__init__(message)
        self.status, self.reason, self.message = status, reason, message


def is_sensitive(path: str) -> bool:
    parts = [p.lower() for p in Path(path).parts]
    if not parts:
        return False
    if any(fnmatch.fnmatchcase(parts[-1], rule) for rule in SENSITIVE_NAMES):
        return True
    return any(p in SENSITIVE_DIRS for p in parts[:-1])


def language_of(path: str) -> str:
    return LANGUAGES.get(Path(path).suffix.lower(), "")


def resolve_inside(path: str, roots: Iterable[str]) -> Path:
    """Real path (links resolved) inside one of the roots. A relative path counts from the first root."""
    roots = [r for r in roots if r]
    if not path or "\x00" in path or not roots:
        raise CodeReadError(400, "invalid", "caminho inválido")
    try:
        real = Path(roots[0], path).resolve()
        real_roots = [Path(r).resolve() for r in roots]
    except (OSError, ValueError, RuntimeError):
        raise CodeReadError(400, "invalid", "caminho inválido") from None
    if not any(real == r or real.is_relative_to(r) for r in real_roots):
        raise CodeReadError(403, "outside", "o arquivo está fora da pasta da sessão")
    return real


def read_for_viewer(path: str, roots: Iterable[str]) -> Dict[str, Any]:
    roots = list(roots)
    real = resolve_inside(path, roots)
    # the requested name and the real name: a link called notas.txt that points to .env is also refused
    if is_sensitive(path) or is_sensitive(str(real)):
        raise CodeReadError(403, "sensitive", "arquivo com nome sensível não é exibido")
    try:
        # without following a link in the last component, and without hanging if someone swaps the file for a FIFO
        fd = os.open(real, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
    except FileNotFoundError:
        raise CodeReadError(404, "missing", "o arquivo não existe mais") from None
    except OSError:  # on Windows, opening a folder gives a permission error: the result is the same
        raise CodeReadError(403, "unreadable", "não foi possível abrir o arquivo") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise CodeReadError(403, "unreadable", "não é um arquivo comum")
        if info.st_size > MAX_BYTES:
            raise CodeReadError(413, "too_large", "arquivo acima de 1 MB")
        raw = b""
        while len(raw) <= MAX_BYTES:
            chunk = os.read(fd, MAX_BYTES + 1 - len(raw))
            if not chunk:
                break
            raw += chunk
    finally:
        os.close(fd)
    if len(raw) > MAX_BYTES:
        raise CodeReadError(413, "too_large", "arquivo acima de 1 MB")
    if b"\x00" in raw:
        raise CodeReadError(415, "binary", "arquivo binário não é exibido")
    try:
        text, lossy = raw.decode("utf-8"), False
    except UnicodeDecodeError:
        text, lossy = raw.decode("utf-8", "replace"), True
    return {"path": str(real), "text": text, "lossy": lossy, "sha256": hashlib.sha256(raw).hexdigest(),
            "size": len(raw), "mtime": info.st_mtime, "language": language_of(str(real))}
