"""Liga PTYs, registro de sessões, comandos digitados, memória em Markdown e índice geral."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Dict, Optional, Set

from vulcan_terminal.core.markdown_index import write_if_changed
from vulcan_terminal.core.session_memory import (AGENT_LABELS, GENERAL_INDEX_FILENAME, extract_transcript, memory_path,
                                                 render_general_index, render_session_md, strip_terminal)
from vulcan_terminal.core.sessions import InputTracker, SessionStore

FLUSH_SECONDS = 15.0
NOTEBOOK_DEBOUNCE_SECONDS = 1.0


class SessionHub:
    def __init__(self, app):
        self.app = app
        self.sessions = SessionStore(app.store)
        self.sessions.close_orphans([])  # nenhum PTY sobrevive a um reinício do servidor
        self._trackers: Dict[str, InputTracker] = {}
        self._dirty: Set[str] = set()
        self._lock = threading.Lock()
        self._write_lock = threading.RLock()
        self._stop = threading.Event()
        self._nb_timer: Optional[threading.Timer] = None
        self._nb_lock = threading.Lock()
        self.last_error: Optional[str] = None
        app.notebook.subscribe(self._on_notebook_change)
        self._flusher = threading.Thread(target=self._flush_loop, name="vulcan-memoria", daemon=True)
        self._flusher.start()
        self.write_index()

    # ── ciclo de vida dos terminais ──────────────────────────────────────
    def on_created(self, pty) -> None:
        self.sessions.create(pty.id, pty.title, pty.site, pty.cwd, getattr(pty, "theme", None))
        with self._lock:
            self._trackers[pty.id] = InputTracker()
        pty.subscribe(lambda chunk, p=pty: self._on_output(p, chunk))
        self.write_memory(pty.id)

    def on_input(self, session_id: str, data: bytes) -> None:
        with self._lock:
            tracker = self._trackers.get(session_id)
        if tracker is None:
            return
        commands = tracker.feed(data)
        if commands:
            self.sessions.add_commands(session_id, commands)
            self.mark_dirty(session_id)

    def _on_output(self, pty, chunk: Optional[bytes]) -> None:
        if chunk is None:
            self.finalize(pty)
        else:
            self.mark_dirty(pty.id)

    def mark_dirty(self, session_id: str) -> None:
        with self._lock:
            self._dirty.add(session_id)

    def finalize(self, pty) -> None:
        """Processo terminou, terminal foi fechado ou o app está saindo: encerra e grava a memória."""
        before = self.sessions.get(pty.id)
        was_open = bool(before and before.is_open)
        record = self.sessions.close(pty.id, pty.exit_code)
        with self._lock:
            self._trackers.pop(pty.id, None)
            self._dirty.discard(pty.id)
        if record is not None and was_open:
            self.write_memory(record.id, pty=pty)
            self.on_session_closed(record, pty)

    def finalize_all(self) -> None:
        for pty in self.app.terminals.list():
            self.finalize(pty)

    def on_session_closed(self, record, pty) -> None:
        self.write_index()

    def on_session_changed(self, session_id: str) -> None:
        record = self.sessions.get(session_id)
        if record is None:
            return
        if record.is_open:
            self.mark_dirty(session_id)
        else:
            self.write_memory(session_id)

    def rename(self, session_id: str, title: str) -> None:
        if self.sessions.get(session_id):
            self.sessions.rename(session_id, title)
            self.mark_dirty(session_id)

    # ── memória ──────────────────────────────────────────────────────────
    def _render(self, record, pty=None) -> str:
        nb = self.app.notebook
        tasks = [t for t in nb.tasks if t.terminal == record.id]
        notes = [n for n in nb.notes if n.terminal == record.id]
        if pty is None:
            pty = self.app.terminals.get(record.id)
        if pty is not None:
            transcript, truncated = strip_terminal(pty.history())
        else:
            existing = self._read_memory(record)
            transcript, truncated = extract_transcript(existing) if existing else ("", False)
        return render_session_md(record, tasks, notes, dict(nb.tags), transcript, truncated,
                                 agents=self.agents_for(record.id))

    # ── sessões de agente pareadas ───────────────────────────
    def _agent_service(self):
        return getattr(self.app, "agents", None)  # o hub nasce antes do serviço de agentes

    def agents_for(self, terminal_id: str) -> list:
        """Sessões de agente pareadas com a aba, completas (arquivos e comandos), da mais antiga para a mais nova."""
        service = self._agent_service()
        if service is None:
            return []
        ids = [aid for aid, pair in service.pairs().items() if pair["terminal_id"] == terminal_id]
        found = [s for s in (service.index.session(i) for i in ids) if s is not None]
        return sorted(found, key=lambda s: s.started_at)

    def agent_tags(self) -> Dict[str, list]:
        """{aba: [{id, agent}]} para a árvore de sessões e o índice geral, a partir da lista leve."""
        service = self._agent_service()
        if service is None:
            return {}
        out: Dict[str, list] = {}
        for s in service.decorate(service.index.sessions()):
            if s.pairing_id:
                out.setdefault(s.pairing_id, []).append({"id": s.id, "agent": s.agent})
        return out

    def _read_memory(self, record) -> Optional[str]:
        path = Path(record.memory_file) if record.memory_file else None
        if path and path.is_file():
            try:
                return path.read_text(encoding="utf-8")
            except OSError:
                return None
        return None

    def write_memory(self, session_id: str, pty=None, index: bool = True) -> Optional[Path]:
        with self._write_lock:
            record = self.sessions.get(session_id)
            if record is None:
                return None
            path = Path(record.memory_file) if record.memory_file else memory_path(self.app.data_dir, record)
            content = self._render(record, pty)
            write_if_changed(path, content)
            self.sessions.set_memory_file(record.id, str(path))
        if index:
            self.write_index()
        return path

    # ── índice geral ─────────────────────────────────────────────────────
    def index_path(self) -> Path:
        return Path(self.app.data_dir) / GENERAL_INDEX_FILENAME

    def write_index(self) -> Path:
        nb = self.app.notebook
        with self._write_lock:
            labels = {tab: [AGENT_LABELS.get(a["agent"], a["agent"]) for a in items]
                      for tab, items in self.agent_tags().items()}
            content = render_general_index(self.sessions.list(), list(nb.tasks), list(nb.notes), dict(nb.tags),
                                           self.app.data_dir, labels)
            write_if_changed(self.index_path(), content)
        return self.index_path()

    def memory_text(self, record) -> Optional[str]:
        if record.is_open and self.app.terminals.get(record.id) is not None:
            return self._render(record)
        return self._read_memory(record)

    def _flush_loop(self) -> None:
        while not self._stop.wait(FLUSH_SECONDS):
            self._flush_once()

    def _flush_once(self) -> None:
        """Uma volta da thread de gravação: nenhuma exceção a derruba."""
        try:
            self.flush()
        except Exception as exc:  # noqa: BLE001  a próxima volta tenta de novo
            self._error(exc)

    def flush(self) -> None:
        """Grava as memórias pendentes e o índice geral uma vez só no fim."""
        with self._lock:
            dirty, self._dirty = self._dirty, set()
        wrote = False
        for session_id in dirty:
            try:
                wrote = self.write_memory(session_id, index=False) is not None or wrote
            except Exception as exc:  # noqa: BLE001  uma sessão com problema não impede as outras
                self.mark_dirty(session_id)
                self._error(exc)
        if wrote:
            self.write_index()

    def _error(self, exc: Exception) -> None:
        """Guarda o último erro na memória e na pasta de dados, para o --doctor (outro processo) ver."""
        self.last_error = f"{type(exc).__name__}: {exc}"
        try:
            self.app.store.save("memoria_status", {"last_error": self.last_error,
                                                   "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        except Exception:  # noqa: BLE001  disco cheio ou pasta sumiu: fica só na memória
            pass

    def _on_notebook_change(self, kind: str) -> None:
        if kind not in ("tasks", "notes", "tags", "all"):
            return
        with self._nb_lock:  # várias threads HTTP mudam o caderno ao mesmo tempo
            if self._nb_timer is not None:
                self._nb_timer.cancel()
            self._nb_timer = threading.Timer(NOTEBOOK_DEBOUNCE_SECONDS, self.refresh_linked_memories)
            self._nb_timer.daemon = True
            self._nb_timer.start()

    def refresh_linked_memories(self) -> None:
        """Tarefas, post-its ou tags mudaram: regrava as memórias das sessões afetadas."""
        nb = self.app.notebook
        linked = {t.terminal for t in nb.tasks if t.terminal} | {n.terminal for n in nb.notes if n.terminal}
        for record in self.sessions.list():
            if record.id in linked or record.tags or record.memory_file:
                if record.is_open:
                    self.mark_dirty(record.id)
                else:
                    self.write_memory(record.id)
        self.write_index()

    def stop(self) -> None:
        self._stop.set()
        if self._nb_timer is not None:
            self._nb_timer.cancel()
