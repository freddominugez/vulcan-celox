"""Estado real do PR pelo `gh` do próprio usuário. Só roda com a preferência ligada, porque consulta a rede."""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

TTL = 60.0
TIMEOUT = 15.0
GH_PLACES = ("/opt/homebrew/bin/gh", "/usr/local/bin/gh", "/usr/bin/gh")
FIELDS = "number,state,isDraft,url,statusCheckRollup"
GOOD = {"SUCCESS", "NEUTRAL", "SKIPPED"}
BAD = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"}


def gh_bin(env: Mapping[str, str], extra: Sequence[str] = GH_PLACES) -> Optional[str]:
    """O app aberto pelo Finder tem PATH curto, por isso também olha nos lugares de costume. VULCAN_GH_BIN manda."""
    if "VULCAN_GH_BIN" in env:
        chosen = env["VULCAN_GH_BIN"]
        return chosen or None
    found = shutil.which("gh", path=env.get("PATH"))
    return found or next((p for p in extra if os.access(p, os.X_OK)), None)


def checks_summary(rollup: Any) -> Dict[str, int]:
    summary = {"total": 0, "passed": 0, "failed": 0, "pending": 0}
    for item in rollup if isinstance(rollup, list) else []:
        if not isinstance(item, dict):
            continue
        summary["total"] += 1
        result = str(item.get("conclusion") or item.get("state") or "").upper()
        key = "passed" if result in GOOD else "failed" if result in BAD else "pending"
        summary[key] += 1
    return summary


def parse(text: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("number"), int):
        return None
    url = data.get("url") if isinstance(data.get("url"), str) and data["url"].startswith("https://") else ""
    return {"number": data["number"], "state": str(data.get("state") or "").upper(), "draft": data.get("isDraft") is True,
            "url": url, "checks": checks_summary(data.get("statusCheckRollup"))}


class PrStatus:
    def __init__(self, runner, env: Mapping[str, str], clock: Callable[[], float] = time.monotonic):
        self.runner, self.env, self.clock = runner, env, clock
        self.lock = threading.Lock()
        self.cache: Dict[str, Tuple[float, Dict]] = {}

    def status(self, cwd: str) -> Dict[str, Any]:
        """{source: "gh", ...} ou {source: "heuristic", reason}. Quem chama confere a preferência antes."""
        now = self.clock()
        with self.lock:
            cached = self.cache.get(cwd)
        if cached and now - cached[0] < TTL:
            return cached[1]
        data = self._ask(cwd)
        with self.lock:
            if len(self.cache) > 200:
                self.cache.clear()
            self.cache[cwd] = (now, data)
        return data

    def _ask(self, cwd: str) -> Dict[str, Any]:
        binary = gh_bin(self.env)
        if not binary:
            return {"source": "heuristic", "reason": "no_gh"}
        result = self.runner.run([binary, "pr", "view", "--json", FIELDS], cwd=cwd, timeout=TIMEOUT)
        if result.code in (126, 127):
            return {"source": "heuristic", "reason": "no_gh"}
        if result.timed_out:
            return {"source": "heuristic", "reason": "timeout"}
        if not result.ok:
            text = (result.stderr or result.stdout or "").lower()
            if "no pull requests found" in text or "no open pull requests" in text:
                return {"source": "gh", "reason": "no_pr", "number": None}
            if "auth login" in text or "not logged" in text:
                return {"source": "heuristic", "reason": "no_login"}
            return {"source": "heuristic", "reason": "failed"}
        parsed = parse(result.stdout)
        return {"source": "gh", **parsed} if parsed else {"source": "heuristic", "reason": "invalid"}
