"""Terminal routes (REST and WebSocket) and per-client sending; split from app.py."""

from __future__ import annotations

import json
import queue
import socket
import threading
from pathlib import Path
from typing import Dict

from vulcan_celox.core import themes
from vulcan_celox.core.listening_ports import PortWatcher
from vulcan_celox.core.quick_commands import is_long_running
from vulcan_celox.server.local_http import HttpError, Request
from vulcan_celox.server.websocket import OP_BINARY, OP_TEXT, WebSocket, WebSocketError

AGENT_COMMANDS = {"claude": "claude", "codex": "codex"}  # argv fixo: nada vindo do cliente vira comando

class ClientSender:
    """Queue and sender thread of a WebSocket client. The PTY reader thread only enqueues: a slow or stuck client
    never stops the reading, the other clients or the process. A client that exceeds the limit is disconnected."""

    LIMIT = 4 * 1024 * 1024

    def __init__(self, ws, sock):
        self.ws = ws
        self.sock = sock
        self._queue: "queue.Queue" = queue.Queue()
        self._pending = 0
        self._lock = threading.Lock()
        self.dropped = False
        self._thread = threading.Thread(target=self._run, name="ws-envio", daemon=True)
        self._thread.start()

    def push(self, item) -> None:
        """bytes (terminal output) or str (text message)."""
        if self.dropped:
            return
        size = len(item)
        with self._lock:
            if self._pending + size > self.LIMIT:
                self.dropped = True
            else:
                self._pending += size
        if self.dropped:
            self.kill()
            return
        self._queue.put(item)

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            with self._lock:
                self._pending -= len(item)
            try:
                if isinstance(item, str):
                    self.ws.send_text(item)
                else:
                    self.ws.send(item, OP_BINARY)
            except (OSError, ValueError):
                self.kill()
                return

    def kill(self) -> None:
        """Disconnects the client: the stuck send and the WebSocket read loop exit with an error."""
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def stop(self) -> None:
        self._queue.put(None)
        self._thread.join(timeout=2)


def terminal_size(rows, cols):
    """Rows and columns of the resize, from 1 to 1000; None if the value is unusable."""
    try:
        rows, cols = int(rows), int(cols)
    except (TypeError, ValueError):
        return None
    if not (1 <= rows <= 1000 and 1 <= cols <= 1000):
        return None
    return rows, cols


def register_terminal_api(app) -> None:
    srv = app.server

    @srv.route("GET", "/api/terminals")
    def _list(_req: Request):
        return {"terminals": [s.info() for s in app.terminals.list()]}

    port_watcher = PortWatcher(app.runner)

    @srv.route("GET", "/api/terminals/ports")
    def _ports(_req: Request):
        tabs = [(s.id, s.pid) for s in app.terminals.list() if s.alive]
        return port_watcher.ports(tabs)

    @srv.route("POST", "/api/terminals")
    def _create(req: Request):
        body = req.json()
        site = app.site(body.get("site")) if body.get("site") else None
        if body.get("site") and site is None:
            raise HttpError(404, "site não encontrado")
        from vulcan_celox.server.fs_api import expand
        cwd = str(expand(body["cwd"], app.env)) if body.get("cwd") else (site.path if site else app.env.get("HOME") or str(Path.home()))
        if not Path(cwd).is_dir():
            raise HttpError(400, f"pasta não existe: {cwd}")
        command = (body.get("command") or "").strip() or None
        theme = body.get("theme")
        if theme == "auto":
            theme = app.theme_rotation.take()  # the Novo terminal button uses up the rotation; a chosen theme does not
        elif theme is not None and not themes.is_theme(theme):
            raise HttpError(400, "tema desconhecido")
        agent = body.get("agent")
        if agent in (None, "", "shell"):
            agent = None
        elif agent not in AGENT_COMMANDS:
            raise HttpError(400, "agent deve ser claude, codex ou shell")
        title = str(body.get("title") or (site.name if site else Path(cwd).name or "terminal"))
        size = terminal_size(body.get("rows") or 24, body.get("cols") or 80)
        if size is None:
            raise HttpError(400, "rows e cols devem ser inteiros de 1 a 1000")
        rows, cols = size
        session = app.spawn_terminal(cwd, title, theme, site=site.name if site else None, rows=rows, cols=cols,
                                      command=command, typed=AGENT_COMMANDS[agent] if agent else None)
        return 201, session.info()

    @srv.route("GET", "/api/themes")
    def _themes(_req: Request):
        in_use: Dict[str, list] = {}
        for s in app.terminals.list():
            if s.alive and s.theme:
                in_use.setdefault(s.theme, []).append(s.id)
        return {"themes": themes.public(), "rotation": themes.ROTATION, "next": app.theme_rotation.peek(),
                "in_use": in_use, "css": themes.css(), "new_terminal": app.new_terminal_prefs()}

    @srv.route("PATCH", r"/api/terminals/(?P<tid>[0-9a-f]+)")
    def _rename(req: Request):
        session = app.terminals.get(req.params["tid"])
        if session is None:
            raise HttpError(404, "terminal não encontrado")
        title = str(req.json().get("title") or "").strip()
        if title:
            session.title = title[:60]
            app.hub.rename(session.id, session.title)
        return session.info()

    @srv.route("GET", r"/api/terminals/(?P<tid>[0-9a-f]+)/busy")
    def _busy(req: Request):
        session = app.terminals.get(req.params["tid"])
        if session is None:
            raise HttpError(404, "terminal não encontrado")
        extra = {"long_running": is_long_running(session.command), "command": session.command}
        if not session.alive:
            return {"busy": False, "processes": [], **extra}
        result = app.runner.run(["/usr/bin/pgrep", "-l", "-P", str(session.pid)], timeout=5)
        names = [line.split(None, 1)[-1] for line in result.stdout.splitlines() if line.strip()]
        return {"busy": bool(names), "processes": names, **extra}

    @srv.route("DELETE", r"/api/terminals/(?P<tid>[0-9a-f]+)")
    def _close(req: Request):
        session = app.terminals.get(req.params["tid"])
        if session is None or not app.terminals.close(req.params["tid"]):
            raise HttpError(404, "terminal não encontrado")
        app.hub.finalize(session)
        record = app.hub.sessions.get(session.id)
        return {"ok": True, "memory_file": record.memory_file if record else None}

    @srv.websocket(r"/ws/terminals/(?P<tid>[0-9a-f]+)")
    def _attach(handler, params, _query):
        session = app.terminals.get(params["tid"])
        if session is None:
            raise HttpError(404, "terminal não encontrado")
        origins = tuple(f"http://{h}" for h in srv.allowed_hosts())
        try:
            ws = WebSocket.accept(handler, origins)
        except WebSocketError as err:
            raise HttpError(400, str(err)) from None

        sender = ClientSender(ws, handler.connection)

        def forward(chunk):
            if chunk is None:
                sender.push(json.dumps({"type": "exit", "code": session.exit_code}))
            else:
                sender.push(chunk)

        # the history is queued inside the PTY lock: it comes before any new output
        session.subscribe(forward, prime=lambda history: sender.push(history) if history else None)
        try:
            if not session.alive:
                sender.push(json.dumps({"type": "exit", "code": session.exit_code}))
            while True:
                message = ws.recv()
                if message is None:
                    break
                opcode, data = message
                if opcode == OP_BINARY:
                    app.hub.on_input(session.id, data)
                    session.write(data)
                elif opcode == OP_TEXT:
                    try:
                        msg = json.loads(data.decode("utf-8"))
                    except ValueError:
                        continue
                    if not isinstance(msg, dict):
                        continue
                    if msg.get("type") == "resize":
                        size = terminal_size(msg.get("rows"), msg.get("cols"))
                        if size:
                            session.resize(*size)
                    elif msg.get("type") == "input":
                        raw = str(msg.get("data") or "").encode("utf-8")
                        app.hub.on_input(session.id, raw)
                        session.write(raw)
        except (WebSocketError, OSError):
            pass
        finally:
            session.unsubscribe(forward)
            sender.stop()
            ws.close()
