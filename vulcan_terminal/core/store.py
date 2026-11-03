"""Persistência JSON atômica com schema_version e migração do protótipo (D6)."""

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
DEFAULT_FILE_MODE = 0o644  # arquivos em pasta de projeto (TAREFAS.md opt-in), como o editor criaria
PRIVATE_FILE_MODE = 0o600  # pasta de dados do app: memórias, índices e documentação
PRIVATE_DIR_MODE = 0o700
_PRIVATE_ROOTS: set = set()


def secure_data_dir(root: Path) -> Path:
    """Pasta de dados só do usuário: a raiz e as subpastas 0700, os arquivos 0600. Ajusta também o que já existe
    (instalações até a 0.3.0 gravavam 0644). Não segue links simbólicos."""
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
                # scripts (hook de pareamento, ajudante do php.ini) continuam executáveis, só para o usuário
                executable = os.stat(path).st_mode & 0o100
                os.chmod(path, PRIVATE_DIR_MODE if executable else PRIVATE_FILE_MODE)
    _PRIVATE_ROOTS.add(os.path.realpath(root))
    return root


def in_private_root(path: Path) -> bool:
    """O caminho fica dentro de uma pasta protegida por secure_data_dir (a pasta de dados do app)."""
    real = os.path.realpath(path)
    return any(real == root or real.startswith(root + os.sep) for root in _PRIVATE_ROOTS)


def make_private(path: Path) -> None:
    """Arquivo ou pasta criados depois de secure_data_dir ficam 0600 e 0700, fora da umask. Fora da
    pasta de dados (pasta de projeto) não muda nada."""
    path = Path(path)
    if not path.is_symlink() and in_private_root(path):
        os.chmod(path, PRIVATE_DIR_MODE if path.is_dir() else PRIVATE_FILE_MODE)


def _new_file_mode(path: Path) -> int:
    return PRIVATE_FILE_MODE if in_private_root(path.parent) else DEFAULT_FILE_MODE


def write_text_atomic(path: Path, text: str) -> None:
    """Grava em arquivo temporário no mesmo diretório e troca com os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = path.stat().st_mode & 0o777  # preserva a permissão de um arquivo existente
    except FileNotFoundError:
        mode = _new_file_mode(path)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
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
    # Serializa antes de tocar no disco: se falhar, o arquivo original fica intacto.
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    write_text_atomic(path, text)


def read_json(path: Path, default: Any) -> Any:
    """Lê JSON; arquivo corrompido é renomeado para <nome>.corrupt-<timestamp>."""
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
    """Coleção de arquivos JSON versionados dentro de um diretório de dados."""

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
        return raw  # arquivo sem envelope (formato antigo): aceito como dado bruto

    def save(self, name: str, data: Any) -> None:
        write_json_atomic(self.path(name), {"schema_version": SCHEMA_VERSION, "data": data})

    def exists(self, name: str) -> bool:
        return self.path(name).exists()

    # ── migrações ────────────────────────────────────────────────────────
    def migration_done(self, key: str) -> bool:
        return bool(self.load(MIGRATIONS_FILE, {}).get(key))

    def mark_migration(self, key: str) -> None:
        done = self.load(MIGRATIONS_FILE, {})
        done[key] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.save(MIGRATIONS_FILE, done)


def migrate_legacy(store: Store, legacy_root: Path) -> Dict[str, int]:
    """Copia notes.json e sites.json do protótipo Valet GUI, uma única vez.

    Os arquivos originais nunca são alterados. Notas brutas vão para
    `legacy_notes` (convertidas pelo Notebook) e sites entram em `sites`.
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
    """Lê JSON sem renomear em caso de corrupção (para arquivos que não são nossos)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError, UnicodeDecodeError):
        return default
