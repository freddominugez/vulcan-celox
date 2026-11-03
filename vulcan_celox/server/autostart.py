"""Inicia o ambiente (Lerd ou Valet) junto com o app, em segundo plano, se ele estiver parado."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict

from vulcan_celox.core.i18n import tr

PREFERENCES = "preferences"
PREF_KEY = "autostart_env"


class EnvAutostart:
    def __init__(self, app) -> None:
        self.app = app
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = {"phase": "idle", "message": "", "output": ""}

    # ── preferência ──────────────────────────────────────────────────────
    def enabled(self) -> bool:
        if self.app.env.get("VULCAN_AUTOSTART") == "0":
            return False
        prefs = self.app.store.load(PREFERENCES, {})
        return not isinstance(prefs, dict) or prefs.get(PREF_KEY, True) is not False

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

    # ── execução ─────────────────────────────────────────────────────────
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
        # divide a trava com Iniciar/Parar da interface: nunca duas operações de serviço ao mesmo tempo
        with self.app._service_lock:
            self._set(phase="starting", message=tr("iniciando o {label}", label=backend.label), started_at=time.time())
            result = backend.start()
        lines = (result.output or "").strip().splitlines()
        tail = "\n".join(lines[-20:])
        if result.ok and backend.status().running:
            self._set(phase="ready", message=tr("{label} iniciado", label=backend.label), output=tail, finished_at=time.time())
            return "ready"
        reason = tr("tempo esgotado") if result.timed_out else (lines[-1] if lines else tr("código {code}", code=result.code))
        self._set(phase="failed", message=tr("não foi possível iniciar o {label}: {reason}", label=backend.label, reason=reason), output=tail,
                  finished_at=time.time())
        return "failed"
