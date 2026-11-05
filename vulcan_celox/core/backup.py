"""Backup and restore of the data folder. Restoring only prepares the files: they swap in on the next start, before
anything has the data open, and what was there moves to `.restauros/`. Nothing is deleted."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterator, List, Optional

from vulcan_celox.core.i18n import tr

MANIFEST = "vulcan-backup.json"
FORMAT = 1
ASIDE_DIR = ".restauros"
PENDING_DIR = ".restauro-pendente"
STAGING_PREFIX = ".restauro-preparando-"
PHASE_FILE = ".fase.json"
KEPT_OUT = (ASIDE_DIR, PENDING_DIR)
SQLITE_SIDE_FILES = ("-wal", "-shm", "-journal")
MAX_TOTAL = 50 * 1024 ** 3
MAX_FILES = 500_000
SESSIONS_FILE = "terminal_sessions.json"
SWAP_TRIES = 10  # on Windows, the app being replaced may hold files for a moment after it closes
SWAP_WAIT = 0.5


class BackupError(Exception):
    """Message for the user; the zip was refused or could not be written."""


def _is_temporary(name: str) -> bool:
    return name.endswith(".tmp") and name.startswith(".")


def _backup_files(data_dir: Path) -> Iterator[Path]:
    for folder, dirs, files in os.walk(data_dir, followlinks=False):
        here = Path(folder)
        if here == data_dir:
            dirs[:] = [d for d in dirs if d not in KEPT_OUT and not d.startswith(STAGING_PREFIX)]
        for name in sorted(files):
            path = here / name
            if path.is_symlink() or _is_temporary(name) or name.endswith(SQLITE_SIDE_FILES):
                continue
            yield path


def _sqlite_copy(source: Path, target: Path) -> bool:
    """A consistent copy of a database in use (the agent index keeps writing). False if it is not one."""
    try:
        with open(source, "rb") as fh:
            if fh.read(16) != b"SQLite format 3\x00":
                return False
        src = sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True, timeout=10)
        dst = sqlite3.connect(str(target))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        return True
    except (sqlite3.Error, OSError):
        return False


def create_backup(data_dir, dest_dir, version: str) -> Dict[str, Any]:
    data_dir, dest_dir = Path(data_dir), Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    real_dest, real_data = dest_dir.resolve(), data_dir.resolve()
    if real_dest == real_data or real_data in real_dest.parents:
        raise BackupError(tr("escolha uma pasta fora da pasta de dados do app"))
    target = real_dest / time.strftime("Vulcan-Celox-backup-%Y%m%d-%H%M%S.zip")
    fd, tmp_name = tempfile.mkstemp(prefix=".vulcan-backup-", suffix=".tmp", dir=str(real_dest))
    os.close(fd)
    tmp = Path(tmp_name)
    count = 0
    try:
        os.chmod(tmp, 0o600)
        with tempfile.TemporaryDirectory(prefix="vulcan-backup-") as scratch, \
                zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, allowZip64=True, strict_timestamps=False) as archive:
            for path in _backup_files(data_dir):
                name = path.relative_to(data_dir).as_posix()
                copy = Path(scratch) / "copia.db"
                copy.unlink(missing_ok=True)
                try:
                    archive.write(copy if _sqlite_copy(path, copy) else path, name)
                except FileNotFoundError:
                    continue  # temporary file that went away during the walk
                count += 1
            archive.writestr(MANIFEST, json.dumps({
                "format": FORMAT, "app": "Vulcan Celox", "version": version, "files": count,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "data_dir": str(data_dir)}))
        os.replace(tmp, target)
    except OSError as exc:
        raise BackupError(tr("não foi possível gravar o backup: {reason}", reason=exc)) from None
    finally:
        tmp.unlink(missing_ok=True)
    return {"path": str(target), "files": count, "size": target.stat().st_size}


def _safe_name(name: str) -> bool:
    if not name or name.startswith("/") or "\\" in name or ":" in name:
        return False
    parts = PurePosixPath(name).parts
    return ".." not in parts and "." not in parts and parts[0] not in KEPT_OUT


def read_manifest(archive: zipfile.ZipFile) -> Dict[str, Any]:
    try:
        manifest = json.loads(archive.read(MANIFEST))
    except (KeyError, ValueError):
        raise BackupError(tr("este arquivo não é um backup do Vulcan Celox")) from None
    if not isinstance(manifest, dict) or not isinstance(manifest.get("format"), int):
        raise BackupError(tr("este arquivo não é um backup do Vulcan Celox"))
    if manifest["format"] > FORMAT:
        raise BackupError(tr("este backup veio de uma versão mais nova do app"))
    return manifest


def _check_members(archive: zipfile.ZipFile, data_dir: Path) -> None:
    members = archive.infolist()
    if len(members) > MAX_FILES:
        raise BackupError(tr("o backup tem arquivos demais"))
    total = 0
    for info in members:
        kind = stat.S_IFMT(info.external_attr >> 16)  # zero when the zip does not say: then it is a plain file
        if not _safe_name(info.filename) or kind not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise BackupError(tr("o backup tem um caminho recusado: {name}", name=info.filename))
        total += info.file_size
    if total > MAX_TOTAL:
        raise BackupError(tr("o backup é grande demais"))
    if total > shutil.disk_usage(data_dir).free:
        raise BackupError(tr("não há espaço em disco para restaurar este backup"))


def _clear_folder(folder: Path) -> None:
    """Removes the app's own staging folder, which holds only what was just extracted from the zip."""
    for current, dirs, files in os.walk(folder, topdown=False):
        for name in files:
            os.unlink(os.path.join(current, name))
        for name in dirs:
            os.rmdir(os.path.join(current, name))
    os.rmdir(folder)


def restore_pending(data_dir) -> bool:
    return (Path(data_dir) / PENDING_DIR).is_dir()


def prepare_restore(zip_path, data_dir) -> Dict[str, Any]:
    """Checks the zip and extracts it next to the data. Whatever is wrong with it, the current data stays untouched."""
    data_dir, zip_path = Path(data_dir), Path(zip_path)
    if not zip_path.is_file():
        raise BackupError(tr("arquivo não encontrado"))
    if restore_pending(data_dir):
        raise BackupError(tr("já há uma restauração preparada: reabra o app para aplicá-la"))
    staging = Path(tempfile.mkdtemp(prefix=STAGING_PREFIX, dir=str(data_dir)))
    try:
        with zipfile.ZipFile(zip_path) as archive:
            manifest = read_manifest(archive)
            _check_members(archive, data_dir)
            archive.extractall(staging)
        os.replace(staging, data_dir / PENDING_DIR)
    except (zipfile.BadZipFile, EOFError, OSError, RuntimeError) as exc:
        _clear_folder(staging)
        raise BackupError(tr("o arquivo está danificado ou não é um backup ({reason})", reason=exc)) from None
    except BackupError:
        _clear_folder(staging)
        raise
    return {"version": manifest.get("version"), "created_at": manifest.get("created_at"), "files": manifest.get("files")}


def _entries(folder: Path, skip) -> List[Path]:
    return [p for p in sorted(folder.iterdir()) if p.name not in skip and not p.name.startswith(STAGING_PREFIX)]


def _fix_memory_paths(data_dir: Path, old_root: Optional[str]) -> None:
    """A backup from another folder or computer: saved memories keep working in the new place."""
    path = data_dir / SESSIONS_FILE
    new_root = str(data_dir)
    if not old_root or old_root == new_root or not path.is_file():
        return
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    records = doc.get("data") if isinstance(doc, dict) else doc
    for record in records if isinstance(records, list) else []:
        memory = record.get("memory_file") if isinstance(record, dict) else None
        if isinstance(memory, str) and memory.startswith(old_root + os.sep):
            record["memory_file"] = new_root + memory[len(old_root):]
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _move_out(data_dir: Path, aside: Path) -> bool:
    """Moves the current data aside, all or nothing. False if something stayed locked: whatever moved goes back."""
    for attempt in range(SWAP_TRIES):
        moved: List[Path] = []
        try:
            for entry in _entries(data_dir, KEPT_OUT):
                os.replace(entry, aside / entry.name)
                moved.append(entry)
            return True
        except OSError:
            for entry in moved:
                os.replace(aside / entry.name, entry)
            if attempt < SWAP_TRIES - 1:
                time.sleep(SWAP_WAIT)
    return False


def apply_pending_restore(data_dir) -> Optional[Path]:
    """Swaps the prepared backup in, and returns where the old data went. Writes the phase first, so a crash in the
    middle resumes instead of moving restored files away as if they were the old ones. If the current data stays
    locked, the app opens with it untouched, and the restore waits for the next start."""
    data_dir = Path(data_dir)
    pending = data_dir / PENDING_DIR
    if not pending.is_dir():
        return None
    phase_path = pending / PHASE_FILE
    phase = json.loads(phase_path.read_text(encoding="utf-8")) if phase_path.is_file() else {}
    aside = data_dir / ASIDE_DIR / (phase.get("stamp") or time.strftime("%Y%m%d-%H%M%S"))
    if phase.get("step") != "entering":
        aside.mkdir(parents=True, exist_ok=True)
        phase_path.write_text(json.dumps({"step": "leaving", "stamp": aside.name}), encoding="utf-8")
        if not _move_out(data_dir, aside):
            return None
        phase_path.write_text(json.dumps({"step": "entering", "stamp": aside.name}), encoding="utf-8")
    try:
        old_root = json.loads((pending / MANIFEST).read_text(encoding="utf-8")).get("data_dir")
    except (OSError, ValueError):
        old_root = None
    for entry in _entries(pending, (PHASE_FILE, MANIFEST)):
        os.replace(entry, data_dir / entry.name)
    _fix_memory_paths(data_dir, old_root)
    _clear_folder(pending)
    return aside
