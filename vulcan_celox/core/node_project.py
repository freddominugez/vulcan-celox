"""Node project reader. Read-only.

Reads the root `package.json`, the lockfile (to know the package manager), the requested Node version, local Supabase
(`supabase/config.toml`) and the Vercel link (`.vercel/project.json`, only `projectId` and `orgId`). Never opens
`.env`: a project's environment variables may hold secrets. Each file has a 1 MB limit; an invalid `package.json`
becomes `estado: ilegivel` with the error, never an empty project.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from vulcan_celox.core.i18n import tr

MAX_FILE = 1024 * 1024
SCRIPT_NAME = re.compile(r"^[A-Za-z0-9:_.-]{1,64}$")

# ordem importa: o primeiro lockfile encontrado decide
LOCKFILES = (
    ("pnpm-lock.yaml", "pnpm"),
    ("bun.lock", "bun"),
    ("bun.lockb", "bun"),
    ("yarn.lock", "yarn"),
    ("package-lock.json", "npm"),
)
# (dependency, display name, default dev server port)
FRAMEWORKS = (
    ("next", "Next.js", 3000),
    ("nuxt", "Nuxt", 3000),
    ("@sveltejs/kit", "SvelteKit", 5173),
    ("astro", "Astro", 4321),
    ("@remix-run/dev", "Remix", 5173),
    ("@react-router/dev", "React Router", 5173),
    ("@nestjs/core", "NestJS", 3000),
    ("vite", "Vite", 5173),
    ("express", "Express", 3000),
)
_PORT_FLAG = re.compile(r"(?:--port[= ]|-p[= ]?)(\d{2,5})\b")
_TOML_SECTION = re.compile(r"^\s*\[([A-Za-z0-9_.-]+)\]\s*$")
_TOML_PAIR = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.+?)\s*(?:#.*)?$")


class Unreadable(Exception):
    pass


def _read_text(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise Unreadable(f"{path.name}: {exc.strerror or exc}") from None
    if size > MAX_FILE:
        raise Unreadable(f"{path.name}: maior que 1 MB")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read(MAX_FILE + 1)
    except (OSError, UnicodeDecodeError) as exc:
        raise Unreadable(f"{path.name}: {exc}") from None


def _optional_text(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    try:
        return _read_text(path)
    except Unreadable:
        return None


def manager(root: Path) -> str:
    for name, pm in LOCKFILES:
        if (root / name).is_file():
            return pm
    return "npm"


def _deps(pkg: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key in ("devDependencies", "dependencies"):
        value = pkg.get(key)
        if isinstance(value, dict):
            out.update({str(k): str(v) for k, v in value.items()})
    return out


def framework(pkg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    deps = _deps(pkg)
    for dep, label, port in FRAMEWORKS:
        if dep in deps:
            return {"id": dep, "nome": label, "porta_padrao": port, "versao": deps[dep]}
    return None


def probable_port(scripts: Dict[str, str], fw: Optional[Dict[str, Any]]) -> Optional[int]:
    dev = scripts.get("dev") or scripts.get("start") or ""
    match = _PORT_FLAG.search(dev)
    if match:
        port = int(match.group(1))
        if 0 < port < 65536:
            return port
    return fw["porta_padrao"] if fw else None


def node_version(root: Path, pkg: Dict[str, Any]) -> Optional[Dict[str, str]]:
    for name in (".nvmrc", ".node-version"):
        text = _optional_text(root / name)
        if text and text.strip():
            return {"valor": text.strip().splitlines()[0][:40], "fonte": name}
    engines = pkg.get("engines")
    if isinstance(engines, dict) and isinstance(engines.get("node"), str):
        return {"valor": engines["node"][:40], "fonte": "engines.node"}
    return None


def _toml_value(raw: str) -> Any:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    if raw.isdigit():
        return int(raw)
    if raw in ("true", "false"):
        return raw == "true"
    return raw


def supabase(root: Path) -> Optional[Dict[str, Any]]:
    """Only what the screen uses: `project_id` and the API port. The rest of config.toml is not interpreted."""
    path = root / "supabase" / "config.toml"
    if not path.is_file():
        return None
    try:
        text = _read_text(path)
    except Unreadable as exc:
        return {"estado": "ilegivel", "erro": tr(str(exc))}
    section = ""
    values: Dict[str, Dict[str, Any]] = {"": {}}
    for line in text.splitlines():
        sec = _TOML_SECTION.match(line)
        if sec:
            section = sec.group(1)
            values.setdefault(section, {})
            continue
        pair = _TOML_PAIR.match(line)
        if pair and not line.lstrip().startswith("#"):
            values.setdefault(section, {})[pair.group(1)] = _toml_value(pair.group(2))
    api = values.get("api", {})
    port = api.get("port") if isinstance(api.get("port"), int) else 54321
    project_id = values[""].get("project_id")
    return {"estado": "ok", "project_id": project_id if isinstance(project_id, str) else None, "porta_api": port,
            "studio": values.get("studio", {}).get("port") if isinstance(values.get("studio", {}).get("port"), int) else 54323}


def vercel(root: Path) -> Optional[Dict[str, Any]]:
    path = root / ".vercel" / "project.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(_read_text(path))
    except (Unreadable, ValueError) as exc:
        return {"estado": "ilegivel", "erro": tr(str(exc))}
    if not isinstance(data, dict):
        return {"estado": "ilegivel", "erro": tr("project.json não é um objeto")}
    # identifiers only; the file holds no token, but nothing beyond these fields leaves here
    return {"estado": "ok", "projectId": str(data.get("projectId") or "")[:80] or None,
            "orgId": str(data.get("orgId") or "")[:80] or None}


def read(root: Path) -> Dict[str, Any]:
    root = Path(root)
    pkg_path = root / "package.json"
    if not pkg_path.is_file():
        return {"estado": "nenhum", "pasta": str(root)}
    try:
        pkg = json.loads(_read_text(pkg_path))
        if not isinstance(pkg, dict):
            raise Unreadable("package.json não é um objeto")
    except ValueError as exc:
        return {"estado": "ilegivel", "pasta": str(root), "erro": tr("package.json: JSON inválido ({exc})", exc=exc)}
    except Unreadable as exc:
        return {"estado": "ilegivel", "pasta": str(root), "erro": tr(str(exc))}
    raw_scripts = pkg.get("scripts") if isinstance(pkg.get("scripts"), dict) else {}
    scripts = {str(k): str(v) for k, v in raw_scripts.items() if SCRIPT_NAME.match(str(k)) and isinstance(v, str)}
    fw = framework(pkg)
    return {
        "estado": "ok",
        "pasta": str(root),
        "nome": str(pkg.get("name") or root.name)[:120],
        "versao": str(pkg.get("version") or "")[:40] or None,
        "gerenciador": manager(root),
        "scripts": [{"nome": k, "comando": v[:400]} for k, v in scripts.items()],
        "framework": fw,
        "porta_provavel": probable_port(scripts, fw),
        "node": node_version(root, pkg),
        "supabase": supabase(root),
        "vercel": vercel(root),
    }


def run_command(pm: str, script: str) -> str:
    """Line typed in the terminal to run a script. Values already validated: known manager and safe name."""
    if pm not in {p for _, p in LOCKFILES}:
        raise ValueError("gerenciador desconhecido")
    if not SCRIPT_NAME.match(script):
        raise ValueError("nome de script inválido")
    return f"{pm} run {script}"


_LOCAL_URL = re.compile(r"https?://(?:localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0):(\d{2,5})\S*")


def local_url(text: str) -> Optional[str]:
    """First local URL seen in a dev server's output (Next, Vite, Nuxt, Astro...)."""
    clean = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)
    match = _LOCAL_URL.search(clean)
    if not match:
        return None
    url = match.group(0).rstrip(".,;)")
    return url.replace("0.0.0.0", "localhost")


def scripts_list(info: Dict[str, Any]) -> List[str]:
    return [s["nome"] for s in info.get("scripts", [])]
