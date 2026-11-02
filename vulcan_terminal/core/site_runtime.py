"""PHP e Node que o backend usa para um site (vt-04 C1), e se a aba do terminal chega neles pelos shims do Lerd."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Dict

WHICH_FIELDS = {"Site": "site", "PHP": "php", "Node": "node", "Document root": "docroot", "Nginx config": "nginx"}
PHP_VERSION = re.compile(r"^PHP (\d+\.\d+\.\d+)", re.MULTILINE)


def parse_which(text: str) -> Dict[str, str]:
    """Saída de `lerd which` (rótulo e valor alinhados por espaços); vazio se o site não está registrado."""
    out: Dict[str, str] = {}
    for line in (text or "").splitlines():
        for label, key in WHICH_FIELDS.items():
            match = re.match(rf"^\s*{re.escape(label)}\s{{2,}}(\S.*?)\s*$", line)
            if match:
                out[key] = match.group(1)
    return out


def parse_php_version(text: str) -> str:
    match = PHP_VERSION.search(text or "")
    return match.group(1) if match else ""


def lerd_shims(home: str) -> Path:
    return Path(home) / ".local" / "share" / "lerd" / "bin"


def shim_status(path_value: str, home: str) -> Dict[str, object]:
    """Qual `php` a aba encontra no PATH e se é o shim do Lerd (que segue a versão do site)."""
    found = shutil.which("php", path=path_value)
    shims = lerd_shims(home)
    if found and os.path.dirname(found) == str(shims):
        return {"php_path": found, "ok": True, "warning": ""}
    if not (shims / "php").exists() or str(shims) not in path_value.split(":"):
        return {"php_path": found or "", "ok": False,
                "warning": "os shims do Lerd não estão no PATH da aba (rode lerd path:enable)"}
    return {"php_path": found or "", "ok": False,
            "warning": f"o php da aba ({found}) não é o do Lerd e pode ter outra versão"}
