"""Minimal YAML parser (block style) for Lerd's files. No dependencies.

Supports: maps by indentation, `- item` lists (including lists of maps),
quoted and unquoted scalars, true/false/null, integers, `{}`/`[]` and simple
inline lists, comments. Does not support anchors, multiline (`|`, `>`)
or inline maps with content.
"""

from __future__ import annotations

import re
from typing import Any, List, Tuple

_INT = re.compile(r"^[-+]?\d+$")


class MiniYamlError(ValueError):
    def __init__(self, line: int, message: str):
        super().__init__(f"linha {line}: {message}")
        self.line = line


def _strip_comment(text: str) -> str:
    quote = None
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "#" and (i == 0 or text[i - 1] in " \t"):
            return text[:i].rstrip()
    return text.rstrip()


def scalar(raw: str) -> Any:
    s = raw.strip()
    if s == "" or s in ("~", "null", "Null", "NULL"):
        return None
    if s == "{}":
        return {}
    if s == "[]":
        return []
    if len(s) >= 2 and s[0] == s[-1] == "'":
        return s[1:-1].replace("''", "'")
    if len(s) >= 2 and s[0] == s[-1] == '"':
        return s[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if s in ("true", "True", "TRUE"):
        return True
    if s in ("false", "False", "FALSE"):
        return False
    if _INT.match(s):
        return int(s)
    if s.startswith("[") and s.endswith("]"):
        return [scalar(part) for part in s[1:-1].split(",") if part.strip()]
    return s


def _split_key(text: str, lineno: int) -> Tuple[str, str]:
    if text.endswith(":"):
        key, rest = text[:-1], ""
    else:
        idx = text.find(": ")
        if idx < 0:
            raise MiniYamlError(lineno, f"esperado 'chave: valor', encontrado {text!r}")
        key, rest = text[:idx], text[idx + 2:]
    key = key.strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in "'\"":
        key = key[1:-1]
    if not key:
        raise MiniYamlError(lineno, "chave vazia")
    return key, rest


def _is_item(text: str) -> bool:
    return text == "-" or text.startswith("- ")


def _looks_like_map(text: str) -> bool:
    if text[:1] in ("'", '"', "[", "{"):
        return False
    return text.endswith(":") or ": " in text


class _Parser:
    def __init__(self, source: str):
        self.lines: List[List[Any]] = []  # [indent, text, lineno]
        for lineno, raw in enumerate(source.splitlines(), 1):
            if "\t" in raw[: len(raw) - len(raw.lstrip())]:
                raise MiniYamlError(lineno, "tabulação na indentação")
            text = _strip_comment(raw)
            if not text.strip() or text.strip() in ("---", "..."):
                continue
            indent = len(text) - len(text.lstrip(" "))
            self.lines.append([indent, text.strip(), lineno])
        self.i = 0

    def parse(self) -> Any:
        if not self.lines:
            return None
        value = self.block(self.lines[0][0])
        if self.i < len(self.lines):
            indent, _text, lineno = self.lines[self.i]
            raise MiniYamlError(lineno, f"indentação inesperada ({indent} espaços)")
        return value

    def block(self, indent: int) -> Any:
        _ind, text, _lineno = self.lines[self.i]
        return self.seq(indent) if _is_item(text) else self.mapping(indent)

    def mapping(self, indent: int) -> dict:
        result: dict = {}
        while self.i < len(self.lines):
            ind, text, lineno = self.lines[self.i]
            if ind < indent:
                break
            if ind > indent:
                raise MiniYamlError(lineno, f"indentação inesperada ({ind} espaços, esperado {indent})")
            if _is_item(text):
                break
            key, rest = _split_key(text, lineno)
            self.i += 1
            if rest.strip():
                result[key] = scalar(rest)
                continue
            if self.i < len(self.lines):
                nind, ntext, _ = self.lines[self.i]
                if nind > indent or (nind == indent and _is_item(ntext)):
                    result[key] = self.block(nind)
                    continue
            result[key] = None
        return result

    def seq(self, indent: int) -> list:
        result: list = []
        while self.i < len(self.lines):
            ind, text, lineno = self.lines[self.i]
            if ind != indent or not _is_item(text):
                if ind > indent:
                    raise MiniYamlError(lineno, f"indentação inesperada ({ind} espaços, esperado {indent})")
                break
            content = text[1:].lstrip()
            if not content:
                self.i += 1
                if self.i < len(self.lines) and self.lines[self.i][0] > indent:
                    result.append(self.block(self.lines[self.i][0]))
                else:
                    result.append(None)
                continue
            if _looks_like_map(content):
                # "- key: value" opens a map whose column is that of the content
                offset = len(text) - len(text[1:].lstrip())
                self.lines[self.i] = [indent + offset, content, lineno]
                result.append(self.mapping(indent + offset))
                continue
            result.append(scalar(content))
            self.i += 1
        return result


def loads(source: str) -> Any:
    return _Parser(source).parse()
