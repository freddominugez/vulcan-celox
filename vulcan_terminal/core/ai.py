"""Cliente mínimo da Anthropic Messages API, só com stdlib. O transporte HTTP é injetável para os testes."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

API_BASE = "https://api.anthropic.com"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-5-5"
USER_AGENT = "VulcanTerminal"

# (método, url, cabeçalhos, corpo, timeout) -> (status, corpo)
Transport = Callable[[str, str, Dict[str, str], Optional[bytes], float], Tuple[int, bytes]]


class AiError(Exception):
    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class Completion:
    text: str
    model: str
    stop_reason: str = ""
    usage: Dict[str, Any] = field(default_factory=dict)


def urllib_transport(method: str, url: str, headers: Dict[str, str], body: Optional[bytes],
                     timeout: float) -> Tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() or b""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise AiError(f"sem conexão com a Anthropic ({reason})") from None


class AnthropicClient:
    def __init__(self, api_key: str, transport: Optional[Transport] = None, base: str = API_BASE,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._key = api_key
        self.transport = transport or urllib_transport
        self.base = base.rstrip("/")
        self.sleep = sleep

    def _headers(self) -> Dict[str, str]:
        return {"x-api-key": self._key, "anthropic-version": API_VERSION, "content-type": "application/json",
                "user-agent": USER_AGENT}

    def _clean(self, text: str) -> str:
        return text.replace(self._key, "[chave]") if self._key else text

    def _call(self, method: str, path: str, payload: Optional[Dict[str, Any]], timeout: float) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        for attempt in range(2):
            status, raw = self.transport(method, f"{self.base}{path}", self._headers(), body, timeout)
            if status in (429, 500, 502, 503, 504, 529) and attempt == 0:
                self.sleep(4.0 if status == 429 else 2.0)
                continue
            break
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            data = {}
        if 200 <= status < 300:
            return data
        detail = self._clean(str((data.get("error") or {}).get("message") or "")).strip()
        if status in (401, 403):
            message = "chave recusada pela Anthropic (inválida ou sem permissão)"
        elif status == 404:
            message = "modelo ou recurso não encontrado na Anthropic"
        elif status == 429:
            message = "limite de uso da Anthropic atingido; tente de novo em instantes"
        elif status == 400:
            message = "a Anthropic recusou o pedido"
        elif status >= 500:
            message = "a Anthropic está indisponível no momento"
        else:
            message = f"resposta inesperada da Anthropic (HTTP {status})"
        raise AiError(f"{message}: {detail}" if detail else message, status)

    def list_models(self, timeout: float = 20.0) -> List[Dict[str, str]]:
        data = self._call("GET", "/v1/models?limit=100", None, timeout)
        return [{"id": str(m.get("id")), "name": str(m.get("display_name") or m.get("id"))}
                for m in data.get("data", []) if m.get("id")]

    def complete(self, system: str, prompt: str, model: str = DEFAULT_MODEL, max_tokens: int = 8000,
                 timeout: float = 300.0) -> Completion:
        payload = {"model": model, "max_tokens": max_tokens, "system": system,
                   "messages": [{"role": "user", "content": prompt}]}
        data = self._call("POST", "/v1/messages", payload, timeout)
        if data.get("stop_reason") == "refusal":  # O texto parcial não pode virar documento
            details = data.get("stop_details") if isinstance(data.get("stop_details"), dict) else {}
            category = f" (categoria: {details['category']})" if details.get("category") else ""
            raise AiError(f"a Anthropic recusou o pedido{category}; tente outro modelo ou reduza o texto enviado")
        text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
        if not text.strip():
            raise AiError("a Anthropic respondeu sem texto")
        return Completion(text=text, model=str(data.get("model") or model), stop_reason=str(data.get("stop_reason") or ""),
                          usage=data.get("usage") or {})
