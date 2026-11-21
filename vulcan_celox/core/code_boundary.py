"""Walk canonical project paths without following a directory that was replaced by a symlink."""

import errno
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Optional


def _walk_from_disk_root(path: Path, flags: int) -> int:
    fd = os.open(path.anchor, flags)
    reached = Path(path.anchor)
    try:
        for part in path.parts[1:]:
            reached = reached / part
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
    except PermissionError as err:
        os.close(fd)
        err.vulcan_reached = reached  # the folder that could not be opened
        raise
    except BaseException:
        os.close(fd)
        raise
    return fd


def _walk_from_root(path: Path, root: Path, flags: int) -> int:
    """Opens the approved root itself and walks only the components below it.

    Residual risk, accepted: the folders ABOVE the root are traversed by the kernel, following links. The opened
    folder must still be the root's current identity (same st_dev/st_ino, canonical path unchanged), so a swap above
    the root before or after the open is refused, never followed into another tree."""
    below = path.relative_to(root).parts
    fd = os.open(str(root), flags)
    try:
        opened, current = os.fstat(fd), os.stat(root)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino) or Path(root).resolve(strict=True) != root:
            raise OSError(errno.ELOOP, "a raiz aprovada mudou durante a abertura", str(root))
        for part in below:
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
    except BaseException:
        os.close(fd)
        raise
    return fd


@contextmanager
def directory(path: Path, root: Optional[Path] = None):
    """File descriptor of `path`, reached without following links.

    `root` (optional) is the approved canonical root that contains `path`. Without it, or when every folder from `/`
    can be opened, the walk starts at `/` as before. Only when a folder strictly above the root refuses to be read
    (0711, 0111, shared hosting ACLs) does the walk anchor on the root itself."""
    if os.scandir not in os.supports_fd or os.open not in os.supports_dir_fd:
        if path.resolve() != path:
            raise NotADirectoryError(str(path))
        yield path
        if path.resolve() != path:
            raise NotADirectoryError(str(path))
        return

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        fd = _walk_from_disk_root(path, flags)
    except PermissionError as err:
        reached = getattr(err, "vulcan_reached", None)
        anchor = Path(root) if root is not None else None
        if anchor is None or reached is None or reached == anchor or not _strictly_above(reached, anchor) \
                or not _inside(path, anchor):
            raise
        fd = _walk_from_root(path, anchor, flags)
    try:
        yield fd
    finally:
        os.close(fd)


def _strictly_above(folder: Path, root: Path) -> bool:
    return folder != root and root.is_relative_to(folder)


def _inside(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def open_file(path: Path, flags: int, root: Optional[Path] = None) -> int:
    if os.open in os.supports_dir_fd and os.scandir in os.supports_fd:
        with directory(path.parent, root) as parent:
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
