"""WebSocket mínimo (RFC 6455) sobre o socket de um BaseHTTPRequestHandler."""

from __future__ import annotations

import base64
import hashlib
import os
import struct
import threading
from typing import BinaryIO, Optional, Tuple

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
OP_CONT, OP_TEXT, OP_BINARY, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA
MAX_MESSAGE = 16 * 1024 * 1024


class WebSocketError(Exception):
    pass


def accept_key(key: str) -> str:
    return base64.b64encode(hashlib.sha1((key + GUID).encode("ascii")).digest()).decode("ascii")


def encode_frame(payload: bytes, opcode: int = OP_BINARY, mask: bool = False, fin: bool = True) -> bytes:
    head = bytearray([(0x80 if fin else 0) | opcode])
    length = len(payload)
    mask_bit = 0x80 if mask else 0
    if length < 126:
        head.append(mask_bit | length)
    elif length < 65536:
        head.append(mask_bit | 126)
        head += struct.pack("!H", length)
    else:
        head.append(mask_bit | 127)
        head += struct.pack("!Q", length)
    if mask:
        key = os.urandom(4)
        head += key
        payload = bytes(b ^ key[i % 4] for i, b in enumerate(payload))
    return bytes(head) + payload


def _read_exact(stream: BinaryIO, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = stream.read(n - len(data))
        if not chunk:
            raise EOFError("conexão fechada")
        data += chunk
    return data


def read_frame(stream: BinaryIO) -> Tuple[bool, int, bytes]:
    b1, b2 = _read_exact(stream, 2)
    fin, opcode = bool(b1 & 0x80), b1 & 0x0F
    masked, length = bool(b2 & 0x80), b2 & 0x7F
    if length == 126:
        length = struct.unpack("!H", _read_exact(stream, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _read_exact(stream, 8))[0]
    if length > MAX_MESSAGE:
        raise WebSocketError("frame grande demais")
    key = _read_exact(stream, 4) if masked else b""
    payload = _read_exact(stream, length)
    if masked:
        payload = bytes(b ^ key[i % 4] for i, b in enumerate(payload))
    return fin, opcode, payload


class WebSocket:
    def __init__(self, rfile: BinaryIO, wfile: BinaryIO, client_masks: bool = True):
        self.rfile = rfile
        self.wfile = wfile
        self.client_masks = client_masks
        self._send_lock = threading.Lock()
        self.closed = False

    @classmethod
    def accept(cls, handler, allowed_origins) -> "WebSocket":
        headers = handler.headers
        if (headers.get("Upgrade") or "").lower() != "websocket" or headers.get("Sec-WebSocket-Version") != "13":
            raise WebSocketError("pedido de upgrade inválido")
        origin = headers.get("Origin")
        if origin and origin not in allowed_origins:
            raise WebSocketError("origem não permitida")
        key = headers.get("Sec-WebSocket-Key")
        if not key:
            raise WebSocketError("Sec-WebSocket-Key ausente")
        handler.send_response(101, "Switching Protocols")
        handler.send_header("Upgrade", "websocket")
        handler.send_header("Connection", "Upgrade")
        handler.send_header("Sec-WebSocket-Accept", accept_key(key))
        handler.end_headers()
        handler.wfile.flush()
        return cls(handler.rfile, handler.wfile)

    def send(self, payload: bytes, opcode: int = OP_BINARY) -> None:
        if self.closed:
            return
        frame = encode_frame(payload, opcode, mask=not self.client_masks)
        with self._send_lock:
            self.wfile.write(frame)
            self.wfile.flush()

    def send_text(self, text: str) -> None:
        self.send(text.encode("utf-8"), OP_TEXT)

    def recv(self) -> Optional[Tuple[int, bytes]]:
        """Próxima mensagem completa (opcode, dados), respondendo ping; None quando fecha."""
        message = bytearray()
        message_op: Optional[int] = None
        while True:
            try:
                fin, opcode, payload = read_frame(self.rfile)
            except (EOFError, OSError):
                self.closed = True
                return None
            if opcode == OP_PING:
                self.send(payload, OP_PONG)
                continue
            if opcode == OP_PONG:
                continue
            if opcode == OP_CLOSE:
                self.close(payload[:2] if len(payload) >= 2 else b"")
                return None
            if opcode in (OP_TEXT, OP_BINARY):
                message_op = opcode
                message = bytearray(payload)
            elif opcode == OP_CONT and message_op is not None:
                message += payload
            else:
                raise WebSocketError(f"opcode inesperado {opcode}")
            if len(message) > MAX_MESSAGE:
                raise WebSocketError("mensagem grande demais")
            if fin:
                return message_op, bytes(message)

    def close(self, code: bytes = b"") -> None:
        if self.closed:
            return
        try:
            self.send(code or struct.pack("!H", 1000), OP_CLOSE)
        except OSError:
            pass
        self.closed = True
