"""Leitura incremental de JSONL: a partir de um offset em bytes, só linhas completas, nunca o arquivo inteiro."""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Tuple, Union

from vulcan_terminal.core.runner import close_pipe, open_pipe

MAX_LINE = 5 * 1024 * 1024
_SKIP_CHUNK = 1024 * 1024


class LineStream:
    """Itera (offset_da_linha, objeto). Depois da iteração, `offset` é onde a próxima leitura deve começar.

    Só consome linhas terminadas em \\n: a última linha de um arquivo que ainda está sendo escrito fica para
    a próxima leitura. JSON inválido, valor que não é objeto e linha acima de `max_line` são registrados em
    `errors` como (offset, motivo) e pulados. Se o arquivo ficou menor que o offset, recomeça do zero e
    marca `reset`.
    """

    def __init__(self, path: Union[str, Path], offset: int = 0, max_line: int = MAX_LINE):
        self.path = Path(path)
        self.offset = max(0, int(offset))
        self.max_line = max_line
        self.errors: List[Tuple[int, str]] = []
        self.reset = False
        self.missing = False
        self.size = 0
        self.on_oversized: Optional[Callable[[int, bytes], None]] = None  # começo da linha descartada

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
                        return  # linha incompleta: tenta de novo na próxima leitura
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
        """Avança até depois do próximo \\n. False se o arquivo acabou antes (linha incompleta)."""
        while True:
            chunk = fh.readline(_SKIP_CHUNK)
            if not chunk:
                return False
            if chunk.endswith(b"\n"):
                return True


class _CountedPipe:
    """Saída de um processo com a interface que LineStream usa: tell() conta os bytes lidos."""

    def __init__(self, raw):
        self.raw, self.position = raw, 0

    def readline(self, limit: int) -> bytes:
        line = self.raw.readline(limit)
        self.position += len(line)
        return line

    def tell(self) -> int:
        return self.position


class ZstdLineStream(LineStream):
    """Um.jsonl.zst lido em stream por `zstd -dcq`, sempre do início: arquivo comprimido não cresce. O offset
    é na saída descomprimida. Sem o comando, ou com arquivo corrompido, registra o erro e devolve o que conseguiu."""

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
    """Forma curta: (ordinal, objeto, offset_seguinte). Erros vão para a lista `errors`, se dada."""
    stream = LineStream(path, offset, max_line)
    for ordinal, (_start, obj) in enumerate(stream):
        yield ordinal, obj, stream.offset
    if errors is not None:
        errors.extend(stream.errors)
