"""Diretórios usados pelo app. Todos sobrescrevíveis por variável de ambiente para testes."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, Optional

ENV_HOME = "VULCAN_CELOX_HOME"
ENV_LEGACY = "VULCAN_LEGACY_HOME"
ENV_VALET_HOME = "VULCAN_VALET_HOME"
ENV_VALET_BIN = "VULCAN_VALET_BIN"

VALET_BIN_CANDIDATES = (
    "/opt/homebrew/bin/valet",
    "/usr/local/bin/valet",
    "~/.composer/vendor/bin/valet",
    "~/.config/composer/vendor/bin/valet",
)


def _env(env: Optional[Mapping[str, str]]) -> Mapping[str, str]:
    return os.environ if env is None else env


def data_dir(env: Optional[Mapping[str, str]] = None) -> Path:
    value = _env(env).get(ENV_HOME)
    if value:
        return Path(value).expanduser()
    from vulcan_celox.core.oscompat import default_data_dir
    return default_data_dir(_env(env))


def legacy_dir(env: Optional[Mapping[str, str]] = None) -> Path:
    """Dados do protótipo Valet GUI."""
    value = _env(env).get(ENV_LEGACY)
    if value:
        return Path(value).expanduser()
    return Path.home() / "Library" / "Application Support" / "ValetGUI"


def valet_home(env: Optional[Mapping[str, str]] = None) -> Path:
    value = _env(env).get(ENV_VALET_HOME)
    if value:
        return Path(value).expanduser()
    return Path.home() / ".config" / "valet"


ENV_LERD_BIN = "VULCAN_LERD_BIN"
ENV_LERD_DATA = "VULCAN_LERD_DATA"
ENV_LERD_API = "VULCAN_LERD_API"

LERD_BIN_CANDIDATES = (
    "~/.local/bin/lerd",
    "/opt/homebrew/bin/lerd",
    "/usr/local/bin/lerd",
)


def lerd_bin_candidates(env: Optional[Mapping[str, str]] = None):
    """Se VULCAN_LERD_BIN estiver definido, só ele é considerado."""
    value = _env(env).get(ENV_LERD_BIN)
    if value:
        return [Path(value).expanduser()]
    return [Path(c).expanduser() for c in LERD_BIN_CANDIDATES]


def lerd_data_dir(env: Optional[Mapping[str, str]] = None) -> Path:
    value = _env(env).get(ENV_LERD_DATA)
    if value:
        return Path(value).expanduser()
    base = _env(env).get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base).expanduser() / "lerd"


def lerd_api_base(env: Optional[Mapping[str, str]] = None) -> str:
    return _env(env).get(ENV_LERD_API) or "http://127.0.0.1:7073"


def valet_bin_candidates(env: Optional[Mapping[str, str]] = None):
    """Se VULCAN_VALET_BIN estiver definido, só ele é considerado."""
    value = _env(env).get(ENV_VALET_BIN)
    if value:
        return [Path(value).expanduser()]
    return [Path(c).expanduser() for c in VALET_BIN_CANDIDATES]
