"""What a backup holds, read from the zip without extracting anything, so the user knows before restoring. Also the
copies a restore left in `.restauros/`, listed and sent to the Trash one by one."""

from __future__ import annotations

import json
import os
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

from vulcan_celox.core.backup import ASIDE_DIR, MANIFEST, STAMP, BackupError, _check_members, read_manifest
from vulcan_celox.core.i18n import tr

MAX_MEMBERS = 20_000
MAX_UNCOMPRESSED = 2 * 1024 ** 3
MAX_COUNTED_FILE = 32 * 1024 * 1024  # a list file bigger than this is not read just to count it
LIST_FILES = {"terminal_sessions": "terminal_sessions.json", "tasks": "tasks.json", "notes": "notes.json"}
AGENT_INDEX = "agentes.db"


def _version_tuple(text: Any) -> tuple:
    parts = []
    for piece in str(text or "").split("-")[0].split("."):
        parts.append(int(piece) if piece.isdigit() else 0)
    return tuple(parts)


def _count_list(archive: zipfile.ZipFile, name: str) -> Optional[int]:
    try:
        info = archive.getinfo(name)
    except KeyError:
        return 0
    if info.file_size > MAX_COUNTED_FILE:
        return None
    try:
        doc = json.loads(archive.read(info))
    except (ValueError, OSError, zipfile.BadZipFile, RuntimeError):
        return None
    records = doc.get("data") if isinstance(doc, dict) and "data" in doc else doc
    return len(records) if isinstance(records, list) else None


def _counts(archive: zipfile.ZipFile) -> Dict[str, Any]:
    counts: Dict[str, Any] = {key: _count_list(archive, name) for key, name in LIST_FILES.items()}
    names = [PurePosixPath(i.filename) for i in archive.infolist() if not i.is_dir()]
    counts["prompts"] = sum(1 for p in names if p.parts[0] == "prompts" and p.suffix == ".md")
    counts["memories"] = sum(1 for p in names if p.parts[0] == "sessoes" and p.suffix == ".md")
    try:
        counts["agent_index"] = archive.getinfo(AGENT_INDEX).file_size
    except KeyError:
        counts["agent_index"] = 0
    return counts


def inspect_backup(zip_path, data_dir, app_version: str) -> Dict[str, Any]:
    """Summary of a backup. `ok` is false when restoring it would be refused; `warnings` says why, or what to notice."""
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        raise BackupError(tr("arquivo não encontrado"))
    warnings: List[Dict[str, str]] = []
    result: Dict[str, Any] = {"path": str(zip_path), "size": zip_path.stat().st_size, "created_at": None,
                              "version": None, "files": None, "counts": None, "warnings": warnings}

    def error(text: str) -> Dict[str, Any]:
        warnings.append({"level": "error", "text": text})
        result["ok"] = False
        return result

    try:
        with zipfile.ZipFile(zip_path) as archive:
            members = archive.infolist()
            if len(members) > MAX_MEMBERS:
                return error(tr("o backup tem mais de {n} arquivos, e não é conferido", n=MAX_MEMBERS))
            if sum(i.file_size for i in members) > MAX_UNCOMPRESSED:
                return error(tr("o backup passa de 2 GB descomprimido, e não é conferido"))
            if MANIFEST not in archive.namelist():
                return error(tr("manifesto ausente: este arquivo não é um backup do Vulcan Celox"))
            try:
                manifest = read_manifest(archive)
            except BackupError as exc:
                return error(str(exc))
            result.update(created_at=manifest.get("created_at"), version=manifest.get("version"),
                          files=manifest.get("files"))
            try:
                _check_members(archive, Path(data_dir))
            except BackupError as exc:
                return error(str(exc))
            result["counts"] = _counts(archive)
    except (zipfile.BadZipFile, EOFError, OSError, RuntimeError) as exc:
        return error(tr("o arquivo está danificado ou não é um backup ({reason})", reason=exc))
    if _version_tuple(result["version"]) > _version_tuple(app_version):
        warnings.append({"level": "warn", "text": tr("o backup veio da versão {version}, mais nova que a do app ({app})",
                                                       version=result["version"], app=app_version)})
    result["ok"] = True
    return result


def _folder_size(folder: Path) -> int:
    total = 0
    for current, _dirs, files in os.walk(folder, followlinks=False):
        for name in files:
            try:
                total += os.lstat(os.path.join(current, name)).st_size
            except OSError:
                pass
    return total


def list_restores(data_dir) -> List[Dict[str, Any]]:
    """The copies a restore moved aside, newest first. Only real folders with a stamp name count."""
    aside = Path(data_dir) / ASIDE_DIR
    if not aside.is_dir():
        return []
    found = []
    for entry in aside.iterdir():
        if entry.is_symlink() or not entry.is_dir() or not STAMP.match(entry.name):
            continue
        when = time.mktime(time.strptime(entry.name, "%Y%m%d-%H%M%S"))
        found.append({"name": entry.name, "at": when, "size": _folder_size(entry)})
    return sorted(found, key=lambda item: item["name"], reverse=True)


def restore_folder(data_dir, name: Any) -> Path:
    """The folder of a listed copy. Any other name, a link or a path with a separator is refused."""
    if not isinstance(name, str) or not STAMP.match(name):
        raise BackupError(tr("cópia de restauração desconhecida"))
    if name not in {item["name"] for item in list_restores(data_dir)}:
        raise BackupError(tr("cópia de restauração desconhecida"))
    return Path(data_dir) / ASIDE_DIR / name
