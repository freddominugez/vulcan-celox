"""Servidor HTTP em loopback com token, verificação de Host, rotas JSON e arquivos estáticos."""

from __future__ import annotations

import hmac
import json
import mimetypes
import posixpath
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Pattern, Tuple
from urllib.parse import parse_qs, urlsplit

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
MAX_BODY = 1024 * 1024
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".json": "application/json",
    ".png": "image/png",
    ".md": "text/markdown; charset=utf-8",
    ".woff2": "font/woff2",
}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self' ws://127.0.0.1:* ws://localhost:*; frame-ancestors 'none'")


class HttpError(Exception):
    def __init__(self, status: int, message: str, extra: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra or {}  # campos a mais no corpo do erro (ex.: needs_confirmation)


class RawResponse:
    """Resposta que não é JSON (CSV de uso). Mesmos cabeçalhos de segurança da API."""

    def __init__(self, body: bytes, content_type: str, filename: Optional[str] = None):
        self.body, self.content_type, self.filename = body, content_type, filename


class Request:
    def __init__(self, handler: "Handler", method: str, match: "re.Match", query: Dict[str, List[str]]):
        self.handler = handler
        self.method = method
        self.params = match.groupdict()
        self.query = query
        self._body: Any = None

    def json(self) -> Dict[str, Any]:
        if self._body is None:
            try:
                length = int(self.handler.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0:
                self.handler.close_connection = True
                raise HttpError(400, "Content-Length inválido")
            if length > MAX_BODY:
                raise HttpError(413, "corpo grande demais")
            raw = self.handler.rfile.read(length) if length else b""
            self.handler.body_consumed = True
            try:
                self._body = json.loads(raw.decode("utf-8")) if raw else {}
            except ValueError:
                raise HttpError(400, "JSON inválido") from None
            if not isinstance(self._body, dict):
                raise HttpError(400, "esperado um objeto JSON")
        return self._body

    def arg(self, name: str, default: Optional[str] = None) -> Optional[str]:
        values = self.query.get(name)
        return values[0] if values else default


Route = Tuple[str, Pattern, Callable[[Request], Any]]


class QuietThreadingServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address) -> None:
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionError, TimeoutError)):
            return  # cliente fechou a conexão (aba, janela ou WebSocket encerrados)
        super().handle_error(request, client_address)


class LocalServer:
    """Roteador + ThreadingHTTPServer. Handlers retornam dados JSON ou levantam HttpError."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0, token: Optional[str] = None,
                 web_root: Path = WEB_ROOT):
        self.token = token or secrets.token_urlsafe(32)
        self.web_root = Path(web_root).resolve()
        # a interface é lida uma vez: reinstalar o app com ele aberto não mistura interface nova com servidor antigo
        self.assets = self._snapshot_assets(self.web_root)
        self.build_id = self.assets_build_id(self.assets)
        self.routes: List[Route] = []
        self.last_api_request = 0.0  # a casca Linux em modo navegador encerra quando a interface para de consultar
        self.ws_routes: List[Tuple[Pattern, Callable]] = []
        server = self

        class _Bound(Handler):
            app = server

        self.httpd = QuietThreadingServer((host, port), _Bound)
        self.port = self.httpd.server_address[1]
        self._thread: Optional[threading.Thread] = None

    @staticmethod
    def assets_build_id(assets: Dict[str, bytes]) -> str:
        """Impressão digital da interface: muda quando uma versão nova é instalada por cima."""
        import hashlib
        digest = hashlib.sha256()
        for rel in sorted(assets):
            digest.update(rel.encode("utf-8"))
            digest.update(hashlib.sha256(assets[rel]).digest())
        return digest.hexdigest()[:16]

    def disk_build_id(self) -> str:
        return self.assets_build_id(self._snapshot_assets(self.web_root))

    @staticmethod
    def _snapshot_assets(root: Path) -> Dict[str, bytes]:
        assets: Dict[str, bytes] = {}
        if not root.is_dir():
            return assets
        for path in root.rglob("*"):
            rel = path.relative_to(root).as_posix()
            if path.is_file() and not any(part.startswith(".") for part in rel.split("/")):
                assets[rel] = path.read_bytes()
        return assets

    # ── registro ─────────────────────────────────────────────────────────
    def route(self, method: str, pattern: str):
        compiled = re.compile("^" + pattern + "$")

        def decorator(fn):
            self.routes.append((method, compiled, fn))
            return fn
        return decorator

    def websocket(self, pattern: str):
        compiled = re.compile("^" + pattern + "$")

        def decorator(fn):
            self.ws_routes.append((compiled, fn))
            return fn
        return decorator

    # ── ciclo de vida ────────────────────────────────────────────────────
    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def allowed_hosts(self) -> Tuple[str, ...]:
        return (f"127.0.0.1:{self.port}", f"localhost:{self.port}")

    def allowed_origins(self) -> Tuple[str, ...]:
        return tuple(f"http://{h}" for h in self.allowed_hosts())

    def start(self) -> "LocalServer":
        self._thread = threading.Thread(target=self.httpd.serve_forever, name="vulcan-http", daemon=True)
        self._thread.start()
        return self

    def serve_forever(self) -> None:
        self.httpd.serve_forever()

    def shutdown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def check_token(self, candidate: Optional[str]) -> bool:
        return bool(candidate) and hmac.compare_digest(candidate.encode(), self.token.encode())


class Handler(BaseHTTPRequestHandler):
    app: LocalServer
    protocol_version = "HTTP/1.1"
    server_version = "VulcanCelox"
    sys_version = ""

    def log_message(self, *_args) -> None:  # silencioso
        pass

    def do_GET(self):  # noqa: N802
        self._dispatch("GET")

    def do_POST(self):  # noqa: N802
        self._dispatch("POST")

    def do_PATCH(self):  # noqa: N802
        self._dispatch("PATCH")

    def do_PUT(self):  # noqa: N802
        self._dispatch("PUT")

    def do_DELETE(self):  # noqa: N802
        self._dispatch("DELETE")

    # ── núcleo ───────────────────────────────────────────────────────────
    def _dispatch(self, method: str) -> None:
        self.body_consumed = False
        try:
            if self.headers.get("Host") not in self.app.allowed_hosts():
                raise HttpError(421, "host não permitido")
            parts = urlsplit(self.path)
            query = parse_qs(parts.query)
            path = parts.path
            if path.startswith("/api/") or path.startswith("/ws/"):
                # Na API o token vem só pelo cabeçalho (força preflight entre origens, que aqui falha);
                # a query vale só no WebSocket, que o navegador não deixa abrir com cabeçalho próprio
                token = self.headers.get("X-Vulcan-Token")
                if path.startswith("/ws/"):
                    token = token or (query.get("token") or [None])[0]
                if not self.app.check_token(token):
                    raise HttpError(401, "token ausente ou inválido")
                origin = self.headers.get("Origin")
                if origin is not None and origin not in self.app.allowed_origins():
                    raise HttpError(403, "origem não permitida")
                if path.startswith("/api/") and method in ("POST", "PUT", "PATCH"):
                    ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                    if ctype != "application/json":
                        raise HttpError(415, "envie Content-Type: application/json")
            if path.startswith("/ws/"):
                self._websocket(path, query)
                return
            if path.startswith("/api/"):
                self.app.last_api_request = time.monotonic()
                self._api(method, path, query)
                return
            if method != "GET":
                raise HttpError(405, "método não permitido")
            self._static(path)
        except HttpError as err:
            self._send_json(err.status, {**err.extra, "error": err.message})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # noqa: BLE001
            self._send_json(500, {"error": f"erro interno: {exc}"})

    def _api(self, method: str, path: str, query) -> None:
        allowed = False
        for route_method, pattern, fn in self.app.routes:
            match = pattern.match(path)
            if not match:
                continue
            allowed = True
            if route_method != method:
                continue
            result = fn(Request(self, method, match, query))
            status = 200
            if isinstance(result, tuple):
                status, result = result
            if isinstance(result, RawResponse):
                self._send_raw(status, result)
                return
            self._send_json(status, result if result is not None else {"ok": True})
            return
        raise HttpError(405 if allowed else 404, "método não permitido" if allowed else "rota não encontrada")

    def _websocket(self, path: str, query) -> None:
        for pattern, fn in self.app.ws_routes:
            match = pattern.match(path)
            if match:
                fn(self, match.groupdict(), query)
                self.close_connection = True
                return
        raise HttpError(404, "rota não encontrada")

    def _static(self, path: str) -> None:
        rel = "index.html" if path in ("", "/") else posixpath.normpath(path.lstrip("/"))
        body = self.app.assets.get(rel)  # só arquivos copiados da pasta web na abertura: sem travessia de caminho
        if body is None:
            raise HttpError(404, "não encontrado")
        target = Path(rel)
        ctype = CONTENT_TYPES.get(target.suffix) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        if target.suffix == ".html":
            self.send_header("Content-Security-Policy", CSP)
        self.end_headers()
        self.wfile.write(body)

    def _discard_unread_body(self) -> None:
        """Corpo que a rota não leu fica no socket e corromperia a próxima requisição da mesma conexão."""
        if getattr(self, "body_consumed", True):
            return
        self.body_consumed = True
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self.close_connection = True
        elif length:
            self.rfile.read(length)

    def _send_raw(self, status: int, raw: "RawResponse") -> None:
        self._discard_unread_body()
        self.send_response(status)
        self.send_header("Content-Type", raw.content_type)
        self.send_header("Content-Length", str(len(raw.body)))
        if raw.filename:
            self.send_header("Content-Disposition", f'attachment; filename="{raw.filename}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw.body)

    def _send_json(self, status: int, data: Any) -> None:
        self._discard_unread_body()
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)
