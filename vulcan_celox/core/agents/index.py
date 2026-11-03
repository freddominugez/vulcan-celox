"""Índice sqlite das sessões de agente em <dados>/agentes.db. Descartável: a fonte da verdade é o JSONL.

Guarda o resumo, o estado do leitor e o offset de cada arquivo para continuar a leitura de onde parou.
Uma sessão cujo JSONL sumiu (o Claude apaga as antigas) continua no índice. Banco corrompido vira
`agentes.db.corrupt-<ts>` e é recriado (D6). Cada mudança incrementa a revisão consultada pela interface.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from vulcan_celox.core.agents import edits as edit_log, history
from vulcan_celox.core.agents.model import AgentSession, CommandRun, FileTouch, SessionEvent, epoch, local_day
from vulcan_celox.core.agents.reading import read_session

# 2: tabela de busca do histórico (FTS5); 3: resumo leve, sem as listas de arquivos e comandos;
# 4: uso por turno (agent_usage), que exige reler todos os arquivos
# 6: estado do turno no resumo, que também só sai relendo; 7: registro das edições (session_edits)
SCHEMA_VERSION = 7
ACTIVE_SECONDS = 90
# o último evento gravado também precisa ser recente: copiar ou restaurar a pasta (backup, Mac novo, clone)
# deixa a data do arquivo nova, mas não muda a data dos eventos; 10 min cobre uma ferramenta longa
ACTIVE_EVENT_SECONDS = 600
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, agent TEXT NOT NULL, file_path TEXT NOT NULL UNIQUE, cwd TEXT, project TEXT, branch TEXT,
  started_at TEXT, last_activity_at TEXT, mtime REAL, file_size INTEGER, byte_offset INTEGER,
  summary TEXT NOT NULL, state TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS sessions_cwd ON sessions(cwd);
CREATE INDEX IF NOT EXISTS sessions_last ON sessions(last_activity_at);
CREATE TABLE IF NOT EXISTS session_files (
  session_id TEXT NOT NULL, path TEXT NOT NULL, kind TEXT, first_at TEXT, last_at TEXT,
  PRIMARY KEY (session_id, path));
CREATE TABLE IF NOT EXISTS session_commands (
  session_id TEXT NOT NULL, seq INTEGER NOT NULL, text TEXT, at TEXT, kind TEXT, exit_code INTEGER,
  PRIMARY KEY (session_id, seq));
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, at TEXT, kind TEXT, text TEXT, tool TEXT);
CREATE INDEX IF NOT EXISTS events_session ON events(session_id, id);
CREATE TABLE IF NOT EXISTS agent_usage (
  session_id TEXT NOT NULL, turn_key TEXT NOT NULL, at TEXT, agent TEXT, model TEXT, input INTEGER, output INTEGER,
  cache_read INTEGER, cache_write_5m INTEGER, cache_write_1h INTEGER, reasoning INTEGER,
  PRIMARY KEY (session_id, turn_key));
CREATE INDEX IF NOT EXISTS agent_usage_at ON agent_usage(at);
CREATE TABLE IF NOT EXISTS parse_errors (file_path TEXT, byte_offset INTEGER, reason TEXT, at REAL);
CREATE INDEX IF NOT EXISTS parse_errors_file ON parse_errors(file_path);
""" + edit_log.SCHEMA
TABLES = ("sessions", "session_files", "session_commands", "events", "parse_errors", "agent_usage", "session_edits")
USAGE_FIELDS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h", "reasoning")
FILE_NAME = "agentes.db"


def index_path(data_dir) -> Path:
    return Path(data_dir) / FILE_NAME


IDENTITY_KEY = "_vt_file"
HEAD_BYTES = 4096


def _split_state(saved: Optional[Dict]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Estado salvo = estado do leitor + identidade do arquivo (inode e começo) guardada junto."""
    if not isinstance(saved, dict):
        return saved, None
    state = dict(saved)
    identity = state.pop(IDENTITY_KEY, None)
    return state, identity if isinstance(identity, dict) else None


def _join_state(state: Dict, identity: Dict) -> Dict:
    return {**(state or {}), IDENTITY_KEY: identity}


def _file_identity(path: str, st, old: Optional[Dict]) -> Dict:
    """Inode e hash do começo do arquivo. Compara o mesmo trecho que foi medido antes: um arquivo que só cresceu
    tem o mesmo começo; um trocado por outro maior não."""
    length = min(int(old.get("len", HEAD_BYTES)) if old else HEAD_BYTES, HEAD_BYTES)
    try:
        with open(path, "rb") as fh:
            head = fh.read(length)
    except OSError:
        head = b""
    if old is None:
        length = len(head)
    return {"ino": st.st_ino, "len": length, "head": hashlib.sha1(head[:length]).hexdigest()}


def _error_text(value: str) -> Optional[str]:
    try:
        data = json.loads(value)
        return f"{data.get('at')}: {data.get('message')}"
    except (TypeError, ValueError, AttributeError):
        return value


def parse_day(day: str) -> Optional[float]:
    """Início do dia local AAAA-MM-DD em segundos."""
    try:
        return datetime.strptime(day, "%Y-%m-%d").astimezone().timestamp()
    except (TypeError, ValueError):
        return None


def is_active(mtime: Optional[float], last_activity_at: Optional[str], now: float) -> bool:
    """Ativa: o arquivo mudou há menos de 90 s e o último evento dentro dele tem menos de 10 min."""
    if not mtime or now - mtime >= ACTIVE_SECONDS:
        return False
    last = epoch(last_activity_at)
    return last is None or now - last < ACTIVE_EVENT_SECONDS


class AgentIndex:
    def __init__(self, path, clock: Callable[[], float] = time.time):
        self.path = Path(path)
        self.clock = clock
        self.lock = threading.RLock()
        self.subagents: Dict[str, int] = {}
        self.corrupt_moved: Optional[Path] = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = self._open()
        self.fts = history.ensure(self.db)
        version = int(self.db.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0])
        if version < SCHEMA_VERSION:
            # o uso por turno (4) e a origem da sessão (5) só saem relendo os arquivos; a varredura
            # seguinte refaz tudo. Também cobre o índice anterior ao resumo leve (esquema 2)
            self.rebuild()
        self.db.execute("UPDATE meta SET value = ? WHERE key = 'schema_version'", (str(SCHEMA_VERSION),))
        self.db.commit()

    # ── abertura ───────────────────────────────────────────────────────────
    def _open(self) -> sqlite3.Connection:
        db = None
        try:
            db = self._connect()
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("quick_check falhou")
            db.executescript(SCHEMA)
        except sqlite3.DatabaseError:
            if db is not None:
                db.close()
            if self.path.exists():
                self.corrupt_moved = self.path.with_name(f"{self.path.name}.corrupt-{int(self.clock())}")
                os.replace(self.path, self.corrupt_moved)
            db = self._connect()
            db.executescript(SCHEMA)
        db.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
        db.execute("INSERT OR IGNORE INTO meta VALUES ('revision', '0')")
        db.commit()
        return db

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(str(self.path), check_same_thread=False, timeout=10)
        db.row_factory = sqlite3.Row
        # WAL: --doctor, --reindexar-agentes e --podar-agentes leem com o app aberto sem "database is locked"
        try:
            db.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            db.close()  # no Windows, arquivo aberto não pode ser movido para o lado
            raise
        for suffix in ("", "-wal", "-shm"):
            try:
                os.chmod(str(self.path) + suffix, 0o600)  # eventos dos agentes: só do usuário
            except OSError:
                pass
        return db

    def close(self) -> None:
        with self.lock:
            self.db.close()

    # ── escrita ────────────────────────────────────────────────────────────
    def revision(self) -> int:
        with self.lock:
            return int(self.db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0])

    def _bump(self) -> None:
        self.db.execute("UPDATE meta SET value = CAST(value AS INTEGER) + 1 WHERE key='revision'")

    def known(self) -> Dict[str, Tuple[float, int]]:
        """file_path -> (mtime, tamanho) do que já foi indexado."""
        with self.lock:
            return {r["file_path"]: (r["mtime"], r["file_size"])
                    for r in self.db.execute("SELECT file_path, mtime, file_size FROM sessions")}

    def update_file(self, agent: str, path, mtime: Optional[float] = None, size: Optional[int] = None) -> Optional[str]:
        """Lê o que for novo no arquivo. Devolve o id da sessão se algo mudou, senão None.

        A leitura e a interpretação do JSONL ficam fora do lock: revision() e as listas da API não
        esperam um arquivo grande. O lock volta só para gravar, e só se ninguém gravou este arquivo no meio."""
        path = str(path)
        try:
            st = os.stat(path)
        except OSError:
            return None
        mtime = st.st_mtime if mtime is None else mtime
        size = st.st_size if size is None else size
        with self.lock:
            row = self.db.execute("SELECT * FROM sessions WHERE file_path = ?", (path,)).fetchone()
            if row and row["mtime"] == mtime and row["file_size"] == size:
                return None
            session = self._full(row) if row else None
            saved = json.loads(row["state"]) if row else None
        base = (row["mtime"], row["file_size"], row["byte_offset"]) if row else None
        state, old_identity = _split_state(saved)
        identity = _file_identity(path, st, old_identity)
        offset = row["byte_offset"] if row else 0
        replaced = old_identity is not None and identity != old_identity  # outro arquivo com o mesmo nome
        if replaced:
            session, state, offset = None, None, 0
        res = read_session(agent, path, session, state, offset)
        s = res.session
        reset = res.reset or replaced
        with self.lock:
            now = self.db.execute("SELECT mtime, file_size, byte_offset FROM sessions WHERE file_path = ?",
                                  (path,)).fetchone()
            if (tuple(now) if now else None) != base:
                return None  # outra leitura gravou este arquivo no meio: a próxima varredura continua dela
            # a mesma sessão em outro caminho: rollout arquivado, pasta renomeada ou duas raízes no CODEX_HOME
            other = self.db.execute("SELECT file_path, mtime FROM sessions WHERE id = ? AND file_path != ?",
                                    (s.id, path)).fetchone()
            if other and os.path.exists(other["file_path"]) and (other["mtime"] or 0) >= mtime:
                return None  # as duas cópias existem: fica a mais recente, e empate mantém a já indexada
            with self.db:
                if row and (reset or row["id"] != s.id):
                    self._forget(row["id"])
                if reset:
                    self.db.execute("DELETE FROM parse_errors WHERE file_path = ?", (path,))
                if other:
                    self._forget(s.id)  # este arquivo foi lido do zero: os eventos do caminho antigo saem
                self._write(s, path, mtime, size, res.offset, _join_state(res.state, identity), res.events,
                            res.errors, res.usage)
                edit_log.store(self.db, s.id, res.edits)
            return s.id

    def note_error(self, message: str) -> None:
        """Último erro do observador, gravado no índice para o --doctor (outro processo) ver."""
        value = json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "message": message[:500]}, ensure_ascii=False)
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('last_error', ?)", (value,))

    def last_error(self) -> Optional[str]:
        with self.lock:
            row = self.db.execute("SELECT value FROM meta WHERE key = 'last_error'").fetchone()
        return _error_text(row[0]) if row else None

    def _write(self, s: AgentSession, path: str, mtime: float, size: int, offset: int, state: Dict,
               events: List[SessionEvent], errors: List[Tuple[int, str]], usage: Optional[List[Dict]] = None) -> None:
        """Grava a sessão (chamar dentro de `with self.db`). O resumo vai leve; arquivos e comandos nas tabelas."""
        self.db.execute(
            "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (s.id, s.agent, path, s.cwd, s.project_name, s.git_branch, s.started_at, s.last_activity_at,
             mtime, size, offset, json.dumps(s.light_dict(), ensure_ascii=False), json.dumps(state)))
        self.db.execute("DELETE FROM session_files WHERE session_id = ?", (s.id,))
        self.db.executemany("INSERT INTO session_files VALUES (?,?,?,?,?)",
                            [(s.id, f.path, f.kind, f.first_at, f.last_at) for f in s.files])
        self.db.execute("DELETE FROM session_commands WHERE session_id = ?", (s.id,))
        first = s.commands_total - len(s.commands)
        self.db.executemany("INSERT INTO session_commands VALUES (?,?,?,?,?,?)",
                            [(s.id, first + i, c.text, c.at, c.kind, c.exit_code) for i, c in enumerate(s.commands)])
        self.db.executemany("INSERT INTO events (session_id, at, kind, text, tool) VALUES (?,?,?,?,?)",
                            [(s.id, e.at, e.kind, e.text, e.tool) for e in events])
        self.db.executemany("INSERT OR REPLACE INTO agent_usage VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            [(s.id, u["key"], u.get("at") or "", s.agent, u.get("model") or "",
                              *(int(u.get(k) or 0) for k in USAGE_FIELDS)) for u in usage or []])
        self.db.executemany("INSERT INTO parse_errors VALUES (?,?,?,?)",
                            [(path, off, reason, self.clock()) for off, reason in errors])
        self._bump()

    def _forget(self, session_id: str) -> None:
        for table, column in (("sessions", "id"), ("session_files", "session_id"),
                              ("session_commands", "session_id"), ("events", "session_id"),
                              ("agent_usage", "session_id"), ("session_edits", "session_id")):
            self.db.execute(f"DELETE FROM {table} WHERE {column} = ?", (session_id,))

    def rebuild(self) -> None:
        """Esvazia o índice; a próxima varredura relê todos os arquivos do zero."""
        with self.lock, self.db:
            for table in TABLES:
                self.db.execute(f"DELETE FROM {table}")
            self._bump()

    def set_subagents(self, counts: Dict[str, int]) -> None:
        with self.lock:
            if counts != self.subagents:
                self.subagents = dict(counts)
                with self.db:
                    self._bump()

    # ── leitura ────────────────────────────────────────────────────────────
    def _hydrate(self, row) -> AgentSession:
        s = AgentSession.from_dict(json.loads(row["summary"]))
        if s.files and not s.files_count:  # resumo de formato antigo, com as listas dentro
            s.files_count, s.edited_count = len(s.files), len(s.edited_files())
        s.is_active = is_active(row["mtime"], s.last_activity_at, self.clock())
        s.subagents = self.subagents.get(s.id, s.subagents)
        return s

    def _full(self, row) -> AgentSession:
        """Resumo com as listas de arquivos e comandos remontadas das tabelas (detalhe e leitura incremental)."""
        s = self._hydrate(row)
        sid = s.id
        files = self.db.execute("SELECT path, kind, first_at, last_at FROM session_files WHERE session_id = ? "
                                "ORDER BY rowid", (sid,)).fetchall()
        if files or not s.files:
            s.files = [FileTouch(r["path"], r["kind"], r["first_at"] or "", r["last_at"] or "") for r in files]
        commands = self.db.execute("SELECT text, at, kind, exit_code FROM session_commands WHERE session_id = ? "
                                   "ORDER BY seq", (sid,)).fetchall()
        if commands or not s.commands:
            s.commands = [CommandRun(r["text"], r["at"] or "", r["kind"] or "shell", r["exit_code"]) for r in commands]
        return s

    def sessions(self) -> List[AgentSession]:
        """Lista leve: sem arquivos nem comandos (use session() para o detalhe)."""
        with self.lock:
            rows = self.db.execute("SELECT summary, mtime FROM sessions ORDER BY last_activity_at DESC").fetchall()
            return [self._hydrate(r) for r in rows]

    def session(self, session_id: str) -> Optional[AgentSession]:
        with self.lock:
            row = self.db.execute("SELECT summary, mtime FROM sessions WHERE id = ?", (session_id,)).fetchone()
            return self._full(row) if row else None

    def edited_on_day(self, day: str, session_ids: Optional[List[str]] = None) -> int:
        """Arquivos editados (não só lidos) cuja última mudança caiu no dia local `day`."""
        start = (parse_day(day) - 86400) if parse_day(day) is not None else 0
        floor = datetime.fromtimestamp(start, timezone.utc).strftime("%Y-%m-%d")  # filtro largo no SQL, exato no Python
        with self.lock:
            rows = self.db.execute("SELECT session_id, last_at FROM session_files WHERE kind != 'read' AND last_at >= ?",
                                   (floor,)).fetchall()
        wanted = set(session_ids) if session_ids is not None else None
        return sum(1 for r in rows if (wanted is None or r["session_id"] in wanted) and local_day(r["last_at"]) == day)

    def prune_events(self, days: int, now: Optional[float] = None) -> int:
        """Apaga os eventos (e a busca) de sessões sem atividade há mais de `days` dias. Resumo, arquivos e
        comandos ficam. Nunca roda sozinho: só por --podar-agentes."""
        cutoff = datetime.fromtimestamp((now if now is not None else self.clock()) - days * 86400, timezone.utc)
        cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%S")
        with self.lock:
            with self.db:
                ids = [r[0] for r in self.db.execute("SELECT id FROM sessions WHERE last_activity_at < ?", (cutoff_iso,))]
                removed = 0
                for sid in ids:
                    removed += self.db.execute("DELETE FROM events WHERE session_id = ?", (sid,)).rowcount
                if removed:
                    self._bump()
            if removed:
                self.db.execute("VACUUM")  # devolve o espaço ao disco
            return removed

    def events(self, session_id: str, start: int = 0, limit: int = 200) -> Tuple[List[SessionEvent], Optional[int]]:
        """Eventos a partir da posição `start`; devolve também a próxima posição, ou None no fim."""
        with self.lock:
            rows = self.db.execute("SELECT at, kind, text, tool FROM events WHERE session_id = ? ORDER BY id "
                                   "LIMIT ? OFFSET ?", (session_id, limit + 1, start)).fetchall()
        more = len(rows) > limit
        return [SessionEvent(r["at"], r["kind"], r["text"], r["tool"]) for r in rows[:limit]], \
            (start + limit if more else None)

    def search(self, q: str = "", kind: Optional[str] = None, agent: Optional[str] = None,
               project: Optional[str] = None, limit: int = 100) -> List[Dict]:
        with self.lock:
            return history.search(self.db, self.fts, q, kind, agent, project, limit)

    def usage_rows(self, since: Optional[str] = None, until: Optional[str] = None,
                   session_id: Optional[str] = None) -> List[Dict]:
        """Linhas de uso por turno com o projeto da sessão. `since`/`until` em ISO UTC (filtro em `at`)."""
        sql = ("SELECT u.*, s.project AS project, s.cwd AS cwd FROM agent_usage u "
               "LEFT JOIN sessions s ON s.id = u.session_id WHERE 1=1")
        args: list = []
        if since:
            sql += " AND u.at >= ?"
            args.append(since)
        if until:
            sql += " AND u.at < ?"
            args.append(until)
        if session_id:
            sql += " AND u.session_id = ?"
            args.append(session_id)
        with self.lock:
            return [dict(r) for r in self.db.execute(sql + " ORDER BY u.at", args)]

    def counts(self) -> Dict[str, int]:
        with self.lock:
            out = {r["agent"]: r["n"] for r in self.db.execute("SELECT agent, COUNT(*) n FROM sessions GROUP BY agent")}
            out["events"] = self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            out["parse_errors"] = self.db.execute("SELECT COUNT(*) FROM parse_errors").fetchone()[0]
            return out
