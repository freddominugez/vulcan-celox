"""Tarefas de IA em segundo plano: uma por alvo, com estado consultável pela interface."""

from __future__ import annotations

import secrets
import threading
import time
from typing import Any, Callable, Dict, List, Tuple

from vulcan_celox.core.ai import AiError
from vulcan_celox.server.local_http import HttpError

KEEP = 30


class AiJobs:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}

    def start(self, kind: str, target: str, label: str, work: Callable[[], Tuple[str, str]]) -> Dict[str, Any]:
        """`work` devolve (arquivo gravado, mensagem). AiError vira mensagem legível; o resto, um erro genérico."""
        with self._lock:
            for job in self._jobs.values():
                if job["status"] == "running" and job["kind"] == kind and job["target"] == target:
                    raise HttpError(409, "já existe uma geração em andamento para este item")
            job = {"id": secrets.token_hex(6), "kind": kind, "target": target, "label": label, "status": "running",
                   "message": "", "file": "", "started_at": time.time(), "finished_at": None}
            self._jobs[job["id"]] = job
            self._trim()
        threading.Thread(target=self._run, args=(job["id"], work), name=f"vulcan-ia-{kind}", daemon=True).start()
        return dict(job)

    def _run(self, job_id: str, work: Callable[[], Tuple[str, str]]) -> None:
        try:
            file, message = work()
            values = {"status": "done", "file": file, "message": message}
        except AiError as exc:
            values = {"status": "failed", "message": exc.message}
        except HttpError as exc:
            values = {"status": "failed", "message": exc.message}
        except Exception as exc:  # noqa: BLE001 - a interface precisa saber que falhou, sem derrubar o servidor
            values = {"status": "failed", "message": f"erro inesperado ({type(exc).__name__})"}
        with self._lock:
            self._jobs[job_id].update(values, finished_at=time.time())

    def _trim(self) -> None:
        finished = sorted((j for j in self._jobs.values() if j["status"] != "running"), key=lambda j: j["started_at"])
        for job in finished[:max(0, len(self._jobs) - KEEP)]:
            self._jobs.pop(job["id"], None)

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            return sorted((dict(j) for j in self._jobs.values()), key=lambda j: j["started_at"], reverse=True)

    def running(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j["status"] == "running")
