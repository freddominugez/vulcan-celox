"""Incremental JSONL reading: from a byte offset, complete lines only, never the whole file."""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Tuple, Union

from vulcan_celox.core.runner import close_pipe, open_pipe

MAX_LINE = 5 * 1024 * 1024
_SKIP_CHUNK = 1024 * 1024


class LineStream:
    """Iterates (line_offset, object). After the iteration, `offset` is where the next read should start.

    Only consumes lines ending in \\n: the last line of a file still being written is left for
    the next read. Invalid JSON, a value that is not an object, and a line above `max_line` are recorded in
    `errors` as (offset, reason) and skipped. If the file became smaller than the offset, it restarts from zero and
    sets `reset`.
    """

    def __init__(self, path: Union[str, Path], offset: int = 0, max_line: int = MAX_LINE):
        self.path = Path(path)
        self.offset = max(0, int(offset))
        self.max_line = max_line
        self.errors: List[Tuple[int, str]] = []
        self.reset = False
        self.missing = False
        self.size = 0
        self.on_oversized: Optional[Callable[[int, bytes], None]] = None  # start of the discarded line

    def __iter__(self) -> Iterator[Tuple[int, dict]]:
        try:
            self.size = os.path.getsize(self.path)
        except OSError:
            self.missing = True
            return
        if self.size < self.offset:
            self.offset = 0
            self.reset = True
        with self._source() as fh:
            while True:
                start = fh.tell()
                raw = fh.readline(self.max_line + 1)
                if not raw:
                    return
                if not raw.endswith(b"\n"):
                    if len(raw) <= self.max_line:
                        return  # incomplete line: try again on the next read
                    if not self._skip_rest(fh):
                        return  # linha grande ainda sendo escrita
                    self.errors.append((start, f"linha acima de {self.max_line} bytes descartada"))
                    if self.on_oversized:
                        self.on_oversized(start, raw)
                    self.offset = fh.tell()
                    continue
                self.offset = fh.tell()
                text = raw.strip()
                if not text:
                    continue
                try:
                    obj = json.loads(text.decode("utf-8", errors="replace"))
                except ValueError:
                    self.errors.append((start, "json inválido"))
                    continue
                if not isinstance(obj, dict):
                    self.errors.append((start, "não é objeto"))
                    continue
                yield start, obj

    @contextlib.contextmanager
    def _source(self):
        with open(self.path, "rb") as fh:
            fh.seek(self.offset)
            yield fh

    @staticmethod
    def _skip_rest(fh) -> bool:
        """Advances past the next \\n. False if the file ended before (incomplete line)."""
        while True:
            chunk = fh.readline(_SKIP_CHUNK)
            if not chunk:
                return False
            if chunk.endswith(b"\n"):
                return True


class _CountedPipe:
    """Output of a process with the interface LineStream uses: tell() counts the bytes read."""

    def __init__(self, raw):
        self.raw, self.position = raw, 0

    def readline(self, limit: int) -> bytes:
        line = self.raw.readline(limit)
        self.position += len(line)
        return line

    def tell(self) -> int:
        return self.position


class ZstdLineStream(LineStream):
    """A .jsonl.zst read as a stream by `zstd -dcq`, always from the start: a compressed file does not grow. The offset
    is in the decompressed output. Without the command, or with a corrupted file, it records the error and returns what it got."""

    def __init__(self, path: Union[str, Path], zstd: Optional[str], max_line: int = MAX_LINE):
        super().__init__(path, 0, max_line)
        self.zstd = zstd

    @contextlib.contextmanager
    def _source(self):
        try:
            if not self.zstd:
                raise OSError("sem o comando zstd")
            proc = open_pipe([self.zstd, "-dcq", "--", str(self.path)])
        except OSError as exc:
            self.errors.append((0, f"zstd não rodou: {exc}"))
            yield io.BytesIO(b"")
            return
        try:
            yield _CountedPipe(proc.stdout)
        finally:
            code = close_pipe(proc)
        if code:
            self.errors.append((self.offset, f"zstd saiu com código {code}: arquivo corrompido?"))


def iter_lines(path: Union[str, Path], offset: int = 0, errors: list = None,
               max_line: int = MAX_LINE) -> Iterator[Tuple[int, dict, int]]:
    """Short form: (ordinal, object, next_offset). Errors go to the `errors` list, if given."""
    stream = LineStream(path, offset, max_line)
    for ordinal, (_start, obj) in enumerate(stream):
        yield ordinal, obj, stream.offset
    if errors is not None:
        errors.extend(stream.errors)
