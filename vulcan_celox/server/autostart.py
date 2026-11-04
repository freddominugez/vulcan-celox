"""Starts the environment (Lerd or Valet) together with the app, in the background, if it is stopped."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict

from vulcan_celox.core.i18n import tr

PREFERENCES = "preferences"
PREF_KEY = "autostart_env"
START_WAIT = 60.0  # after `lerd start` returns, the Podman VM and the panel can still be coming up
POLL_SECONDS = 2.0


def wait_running(backend, seconds: float, sleep=time.sleep):
    """Status of the environment, waiting up to `seconds` for it to respond."""
    deadline = time.monotonic() + seconds
    status = backend.status()
    while not status.running and time.monotonic() < deadline:
        sleep(POLL_SECONDS)
        status = backend.status()
    return status


def failure_reason(result) -> str:
    """Why a start failed. Progress lines ("→ nginx", "... ✓") say nothing about it, so they never become the reason."""
    if result.timed_out:
        return tr("tempo esgotado")
    lines = [line.strip() for line in (result.stderr or "").splitlines() + (result.stdout or "").splitlines() if line.strip()]
    useful = [line for line in lines if not line.startswith(("→", "✓")) and not line.endswith("✓")]
    return useful[-1] if useful else tr("código {code}", code=result.code)


class EnvAutostart:
    start_wait = START_WAIT

    def __init__(self, app) -> None:
        self.app = app
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = {"phase": "idle", "message": "", "output": ""}

    # ── preference ─────────────────────────────────────────────────────
    def enabled(self) -> bool:
        if self.app.env.get("VULCAN_AUTOSTART") == "0":
            return False
        prefs = self.app.store.load(PREFERENCES, {})
        return isinstance(prefs, dict) and prefs.get(PREF_KEY) is True  # Lerd is optional: off until the user chooses

    def set_enabled(self, value: bool) -> None:
        prefs = self.app.store.load(PREFERENCES, {})
        prefs = prefs if isinstance(prefs, dict) else {}
        prefs[PREF_KEY] = bool(value)
        self.app.store.save(PREFERENCES, prefs)

    def state(self) -> Dict[str, Any]:
        with self._lock:
            return {**self._state, "enabled": self.enabled()}

    def _set(self, **values: Any) -> None:
        with self._lock:
            self._state.update(values)

    # ── execution ──────────────────────────────────────────────────────
    def begin(self) -> threading.Thread:
        thread = threading.Thread(target=self.run, name="vulcan-autostart", daemon=True)
        thread.start()
        return thread

    def run(self) -> str:
        backend = self.app.backend
        if not self.enabled():
            self._set(phase="skipped", message=tr("início automático desligado"))
            return "skipped"
        if not backend.available:
            self._set(phase="skipped", message=tr("nenhum ambiente instalado"))
            return "skipped"
        self._set(phase="checking", message=tr("verificando o {label}", label=backend.label))
        if backend.status().running:
            self._set(phase="ready", message=tr("{label} já estava rodando", label=backend.label))
            return "ready"
        # shares the lock with the interface Iniciar/Parar: never two service operations at the same time
        with self.app._service_lock:
            self._set(phase="starting", message=tr("iniciando o {label}", label=backend.label), started_at=time.time())
            result = backend.start()
        tail = "\n".join((result.output or "").strip().splitlines()[-20:])
        status = wait_running(backend, self.start_wait) if result.ok else None
        if status is not None and status.running:
            self._set(phase="ready", message=tr("{label} iniciado", label=backend.label), output=tail, finished_at=time.time())
            return "ready"
        reason = failure_reason(result) if status is None else tr("o comando terminou, mas o ambiente não respondeu: {summary}", summary=status.summary)
        self._set(phase="failed", message=tr("não foi possível iniciar o {label}: {reason}", label=backend.label, reason=reason), output=tail,
                  finished_at=time.time())
        return "failed"
