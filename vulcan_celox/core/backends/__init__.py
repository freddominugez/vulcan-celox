"""Environment backend selection: Lerd, then Valet, otherwise local mode."""

from __future__ import annotations

import os
from typing import Mapping, Optional

from vulcan_celox.core import paths
from vulcan_celox.core.backends.base import Backend
from vulcan_celox.core.backends.lerd import LerdBackend
from vulcan_celox.core.backends.null import NullBackend
from vulcan_celox.core.backends.valet import ValetBackend

__all__ = ["Backend", "LerdBackend", "NullBackend", "ValetBackend", "detect_backend"]


def _first_executable(candidates):
    for candidate in candidates:
        if candidate.is_file() and os.access(str(candidate), os.X_OK):
            return candidate
    return None


def detect_backend(env: Optional[Mapping[str, str]] = None, runner=None) -> Backend:
    lerd = _first_executable(paths.lerd_bin_candidates(env))
    if lerd is not None:
        return LerdBackend(lerd, runner=runner, data_dir=paths.lerd_data_dir(env),
                           api_base=paths.lerd_api_base(env))
    home = paths.valet_home(env)
    valet = _first_executable(paths.valet_bin_candidates(env))
    if valet is not None:
        return ValetBackend(valet, runner=runner, valet_home=home)
    return NullBackend(None, runner=runner, valet_home=home)
