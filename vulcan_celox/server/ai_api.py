"""Configuração da IA: chave no Keychain, validação na Anthropic e escolha do modelo. A chave nunca sai do servidor."""

from __future__ import annotations

import re
from typing import Any, Dict
from urllib.parse import urlsplit

from vulcan_celox.core.ai import API_BASE, DEFAULT_MODEL, AiError, AnthropicClient
from vulcan_celox.core.keychain import SecretError, mask, valid_key
from vulcan_celox.server.local_http import HttpError, Request

PREFERENCES = "preferences"
MODEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.\-]{1,80}$")


class AiConfig:
    def __init__(self, app) -> None:
        self.app = app

    # ── preferências ─────────────────────────────────────────────────────
    def _prefs(self) -> Dict[str, Any]:
        prefs = self.app.store.load(PREFERENCES, {})
        return prefs if isinstance(prefs, dict) else {}

    def _save(self, **values: Any) -> None:
        prefs = self._prefs()
        prefs.update(values)
        self.app.store.save(PREFERENCES, prefs)

    def model(self) -> str:
        value = self._prefs().get("ai_model")
        return value if isinstance(value, str) and MODEL_PATTERN.match(value) else DEFAULT_MODEL

    def models(self):
        value = self._prefs().get("ai_models")
        return value if isinstance(value, list) else []

    # ── chave ────────────────────────────────────────────────────────────
    def key(self):
        return self.app.keystore.get()

    def client(self, key=None) -> AnthropicClient:
        key = key or self.key()
        if not key:
            raise HttpError(409, "configure a chave da Anthropic na tela Índice")
        return AnthropicClient(key, transport=self.app.ai_transport, base=self.base())

    def base(self) -> str:
        """VULCAN_ANTHROPIC_BASE_URL permite proxy corporativo ou servidor de teste local; http só no loopback,
        para a chave nunca sair em claro da máquina."""
        base = self.app.env.get("VULCAN_ANTHROPIC_BASE_URL") or API_BASE
        parts = urlsplit(base)
        if parts.scheme == "https" and parts.hostname:
            return base
        if parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost", "::1"):
            return base
        raise HttpError(400, "VULCAN_ANTHROPIC_BASE_URL precisa ser https (http só para 127.0.0.1 ou localhost)")

    def public(self) -> Dict[str, Any]:
        key = self.key()
        return {"provider": "anthropic", "configured": bool(key), "masked": mask(key), "model": self.model(),
                "models": self.models(), "default_model": DEFAULT_MODEL}


def register_ai_config_api(app) -> AiConfig:
    srv = app.server
    config = AiConfig(app)

    @srv.route("GET", "/api/ai/config")
    def get_config(_req: Request):
        return config.public()

    @srv.route("PUT", "/api/ai/key")
    def put_key(req: Request):
        key = str(req.json().get("key") or "").strip()
        if not valid_key(key):
            raise HttpError(400, "isso não parece uma chave da Anthropic (começa com sk-ant-)")
        try:
            models = config.client(key).list_models()
        except AiError as exc:
            raise HttpError(400, exc.message) from None
        try:
            app.keystore.set(key)
        except SecretError as exc:
            raise HttpError(500, str(exc)) from None
        ids = [m["id"] for m in models]
        values: Dict[str, Any] = {"ai_models": models}
        if ids and config.model() not in ids:
            values["ai_model"] = DEFAULT_MODEL if DEFAULT_MODEL in ids else ids[0]
        config._save(**values)
        return config.public()

    @srv.route("DELETE", "/api/ai/key")
    def delete_key(_req: Request):
        app.keystore.delete()
        return config.public()

    @srv.route("PATCH", "/api/ai/config")
    def patch_config(req: Request):
        model = req.json().get("model")
        if not isinstance(model, str) or not MODEL_PATTERN.match(model):
            raise HttpError(400, "modelo inválido")
        ids = [m["id"] for m in config.models()]
        if ids and model not in ids:
            raise HttpError(400, "modelo não disponível para esta chave")
        config._save(ai_model=model)
        return config.public()

    return config
