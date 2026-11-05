"""Is there a newer stable Release? Only reads the version number from GitHub; it never downloads or installs anything."""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from vulcan_celox.core.ai import AiError, urllib_transport
from vulcan_celox.core.pr_status import gh_bin

REPO = "freddominugez/vulcan-celox"
API_PATH = f"repos/{REPO}/releases/latest"  # "latest" never returns a pre-release
API_URL = f"https://api.github.com/{API_PATH}"
RELEASE_PREFIX = f"https://github.com/{REPO}/releases/"
TIMEOUT = 8.0
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse_version(text: Any) -> Optional[Tuple[int, int, int]]:
    match = _VERSION.match(text) if isinstance(text, str) else None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3))) if match else None


def is_newer(latest: Any, current: Any) -> bool:
    a, b = parse_version(latest), parse_version(current)
    return bool(a and b and a > b)


def _parse(raw: Any) -> Optional[Dict[str, str]]:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    tag, url = data.get("tag_name"), data.get("html_url")
    # the link becomes a button: only this repository's release pages
    if not parse_version(tag) or not isinstance(url, str) or not url.startswith(RELEASE_PREFIX):
        return None
    return {"latest": tag.lstrip("v"), "url": url}


def fetch_latest(env: Mapping[str, str], runner, current: str, transport: Optional[Callable] = None) -> Dict[str, Any]:
    """{"latest", "url"} or {"reason": offline | unavailable | invalid}."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": f"Vulcan-Celox/{current}"}
    try:
        status, body = (transport or urllib_transport)("GET", API_URL, headers, None, TIMEOUT)
    except AiError:
        return {"reason": "offline"}
    if status == 200:
        return _parse(body) or {"reason": "invalid"}
    # the anonymous call sees nothing while the repository is private, or when rate limited: the user's own gh may
    binary = gh_bin(env)
    if not binary:
        return {"reason": "unavailable"}
    result = runner.run([binary, "api", API_PATH], timeout=TIMEOUT)
    if not result.ok or result.timed_out:
        return {"reason": "unavailable"}
    return _parse(result.stdout) or {"reason": "invalid"}
