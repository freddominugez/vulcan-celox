"""Atomic JSON persistence with schema_version and prototype migration."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

SCHEMA_VERSION = 1
MIGRATIONS_FILE = "migrations"
DEFAULT_FILE_MODE = 0o644  # files in a project folder (opt-in TAREFAS.md), as the editor would create them
PRIVATE_FILE_MODE = 0o600  # app data folder: memories, indexes and documentation
PRIVATE_DIR_MODE = 0o700
_PRIVATE_ROOTS: set = set()


def secure_data_dir(root: Path) -> Path:
    """User-only data folder: the root and subfolders 0700, the files 0600. Also adjusts what already exists
        (installs up to 0.3.0 wrote 0644). Does not follow symlinks."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, PRIVATE_DIR_MODE)
    for current, dirs, files in os.walk(root):
        for name in dirs:
            path = os.path.join(current, name)
            if not os.path.islink(path):
                os.chmod(path, PRIVATE_DIR_MODE)
        for name in files:
            path = os.path.join(current, name)
            if not os.path.islink(path):
                # scripts (pairing hook, php.ini helper) stay executable, for the user only
                executable = os.stat(path).st_mode & 0o100
                os.chmod(path, PRIVATE_DIR_MODE if executable else PRIVATE_FILE_MODE)
    _PRIVATE_ROOTS.add(os.path.realpath(root))
    return root


def in_private_root(path: Path) -> bool:
    """The path is inside a folder protected by secure_data_dir (the app's data folder)."""
    real = os.path.realpath(path)
    return any(real == root or real.startswith(root + os.sep) for root in _PRIVATE_ROOTS)


def make_private(path: Path) -> None:
    """A file or folder created after secure_data_dir ends up 0600 and 0700, regardless of umask. Outside the
        data folder (project folder) nothing changes."""
    path = Path(path)
    if not path.is_symlink() and in_private_root(path):
        os.chmod(path, PRIVATE_DIR_MODE if path.is_dir() else PRIVATE_FILE_MODE)


def _new_file_mode(path: Path) -> int:
    return PRIVATE_FILE_MODE if in_private_root(path.parent) else DEFAULT_FILE_MODE


def write_text_atomic(path: Path, text: str) -> None:
    """Writes to a temporary file in the same directory and swaps with os.replace."""
    path = Path(path)
    created = [p for p in (path.parent, *path.parent.parents) if not p.exists()]
    path.parent.mkdir(parents=True, exist_ok=True)
    for folder in created:
        make_private(folder)  # a folder born after the opening, such as sessoes/, is private from the first file on
    try:
        mode = path.stat().st_mode & 0o777  # preserves the permission of an existing file
    except FileNotFoundError:
        mode = _new_file_mode(path)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:  # the text as it came: on Windows, without extra \r\n
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, str(path))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_json_atomic(path: Path, data: Any) -> None:
    # Serialize before touching the disk: if it fails, the original file stays intact.
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    write_text_atomic(path, text)


def read_json(path: Path, default: Any) -> Any:
    """Reads JSON; a corrupted file is renamed to <name>.corrupt-<timestamp>."""
    path = Path(path)
    if not path.exists():
        return copy.deepcopy(default)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (ValueError, UnicodeDecodeError):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        corrupt = path.with_name(f"{path.name}.corrupt-{stamp}")
        n = 1
        while corrupt.exists():
            corrupt = path.with_name(f"{path.name}.corrupt-{stamp}-{n}")
            n += 1
        os.replace(str(path), str(corrupt))
        return copy.deepcopy(default)


class Store:
    """Collection of versioned JSON files inside a data directory."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def path(self, name: str) -> Path:
        return self.root / f"{name}.json"

    def load(self, name: str, default: Any) -> Any:
        raw = read_json(self.path(name), None)
        if raw is None:
            return copy.deepcopy(default)
        if isinstance(raw, dict) and "schema_version" in raw and "data" in raw:
            return raw["data"]
        return raw  # file without an envelope (old format): accepted as raw data

    def save(self, name: str, data: Any) -> None:
        write_json_atomic(self.path(name), {"schema_version": SCHEMA_VERSION, "data": data})

    def exists(self, name: str) -> bool:
        return self.path(name).exists()

    # ── migrations ────────────────────────────────────────────────────
    def _migrations(self) -> Dict[str, Any]:
        data = self.load(MIGRATIONS_FILE, {})
        return data if isinstance(data, dict) else {}

    def migration_done(self, key: str) -> bool:
        return bool(self._migrations().get(key))

    def mark_migration(self, key: str) -> None:
        done = self._migrations()
        done[key] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.save(MIGRATIONS_FILE, done)


def migrate_legacy(store: Store, legacy_root: Path) -> Dict[str, int]:
    """Copies notes.json and sites.json from the Valet GUI prototype, only once.

        The original files are never changed. Raw notes go to
        `legacy_notes` (converted by the Notebook) and sites go into `sites`.
    """
    report = {"notes_sites": 0, "sites": 0, "skipped": 0}
    if store.migration_done("valetgui"):
        report["skipped"] = 1
        return report
    legacy_root = Path(legacy_root)

    notes = read_json_readonly(legacy_root / "notes.json")
    if isinstance(notes, dict) and notes:
        store.save("legacy_notes", notes)
        report["notes_sites"] = len(notes)

    sites = read_json_readonly(legacy_root / "sites.json")
    if isinstance(sites, dict) and sites:
        current = store.load("sites", {})
        for name, path in sites.items():
            if isinstance(name, str) and isinstance(path, str):
                current.setdefault(name, path)
        store.save("sites", current)
        report["sites"] = len(sites)

    store.mark_migration("valetgui")
    return report


def read_json_readonly(path: Path, default: Optional[Any] = None) -> Any:
    """Reads JSON without renaming on corruption (for files that are not ours)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError, UnicodeDecodeError):
        return default
