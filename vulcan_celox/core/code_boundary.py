"""Walk canonical project paths without following a directory that was replaced by a symlink."""

import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def directory(path: Path):
    if os.scandir not in os.supports_fd or os.open not in os.supports_dir_fd:
        if path.resolve() != path:
            raise NotADirectoryError(str(path))
        yield path
        if path.resolve() != path:
            raise NotADirectoryError(str(path))
        return

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(path.anchor, flags)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        os.close(fd)


def open_file(path: Path, flags: int) -> int:
    if os.open in os.supports_dir_fd and os.scandir in os.supports_fd:
        with directory(path.parent) as parent:
            return os.open(path.name, flags, dir_fd=parent)
    if path.resolve() != path:
        raise OSError(str(path))
    fd = os.open(path, flags)
    try:
        if path.resolve() != path:
            raise OSError(str(path))
    except (OSError, RuntimeError):
        os.close(fd)
        raise
    return fd
