import io
import json
import logging
import unittest

from tests.helpers import TempDirTestCase
from tests.server_helpers import ServerTestCase
from vulcan_terminal.core.ai import AiError, AnthropicClient
from vulcan_terminal.core.keychain import KeychainStore, MemoryKeyStore, mask, valid_key
from vulcan_terminal.core.runner import FakeRunner, Result
from vulcan_terminal.server.app import VulcanApp

KEY = "sk-ant-api03-" + "x1Y2z3" * 8  # sintética
MODELS = {"data": [{"id": "claude-sonnet-5-5", "display_name": "Claude Sonnet 5"},
                   {"id": "claude-opus-5", "display_name": "Claude Opus 5"}]}


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": headers, "body": body})
        status, payload = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        return status, json.dumps(payload).encode()


class KeychainTest(TempDirTestCase):
    def test_chave_so_pelo_stdin(self):
        runner = FakeRunner()
        store = KeychainStore(runner=runner)
        runner.respond(["/usr/bin/security", "find-generic-password", "-s", store.service, "-a", "api-key", "-w"],
                       Result(0, KEY + "\n"))
        store.set(KEY)
        add = runner.calls[0]
        self.assertEqual(add.argv, ("/usr/bin/security", "-i"))
        self.assertIn(KEY, add.input)
        for call in runner.calls:
            self.assertNotIn(KEY, " ".join(call.argv))
        self.assertEqual(store.get(), KEY)

    def test_formato_invalido_nao_chama_security(self):
        runner = FakeRunner()
        with self.assertRaises(Exception):
            KeychainStore(runner=runner).set("sk-ant-abc; rm -rf ~")
        self.assertEqual(runner.calls, [])
        self.assertFalse(valid_key("sk-ant-" + "a" * 30 + " -w outro"))
        self.assertEqual(mask(KEY), "sk-ant-…" + KEY[-4:])


class ClientTest(TempDirTestCase):
    def test_erros_legiveis_sem_chave(self):
        t = FakeTransport((401, {"error": {"message": f"invalid x-api-key {KEY}"}}))
        with self.assertRaises(AiError) as ctx:
            AnthropicClient(KEY, transport=t, sleep=lambda s: None).list_models()
        self.assertEqual(ctx.exception.status, 401)
        self.assertNotIn(KEY, ctx.exception.message)
        self.assertEqual(t.calls[0]["headers"]["x-api-key"], KEY)
        self.assertEqual(t.calls[0]["headers"]["anthropic-version"], "2023-06-01")

    def test_nova_tentativa_em_429_e_texto(self):
        waits = []
        t = FakeTransport((429, {}), (200, {"model": "claude-sonnet-5-5", "stop_reason": "end_turn",
                                            "content": [{"type": "text", "text": "# Doc"}]}))
        out = AnthropicClient(KEY, transport=t, sleep=waits.append).complete("sys", "oi")
        self.assertEqual((out.text, len(t.calls), len(waits)), ("# Doc", 2, 1))
        body = json.loads(t.calls[1]["body"])
        self.assertEqual((body["model"], body["messages"][0]["content"]), ("claude-sonnet-5-5", "oi"))


class RecusaTest(unittest.TestCase):
    """Recusa vira erro claro; texto parcial não passa por documento pronto."""

    def test_recusa_com_e_sem_categoria(self):
        for extra, esperado in (({"stop_details": {"type": "refusal", "category": "cyber"}}, "categoria: cyber"), ({}, "recusou"),
                                ({"stop_details": None}, "recusou")):
            t = FakeTransport((200, {"model": "claude-sonnet-5-5", "stop_reason": "refusal",
                                     "content": [{"type": "text", "text": "parcial"}], **extra}))
            with self.assertRaises(AiError) as caught:
                AnthropicClient(KEY, transport=t).complete("sys", "oi")
            self.assertIn(esperado, str(caught.exception))


class AiConfigApiTest(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.log = io.StringIO()
        self.handler = logging.StreamHandler(self.log)
        logging.getLogger().addHandler(self.handler)
        self.app.keystore = MemoryKeyStore()
        self.transport = FakeTransport((200, MODELS))
        self.app.ai_transport = self.transport

    def tearDown(self):
        logging.getLogger().removeHandler(self.handler)
        super().tearDown()

    def test_ciclo_da_chave_sem_vazar(self):
        cfg = self.request("GET", "/api/ai/config")[1]
        self.assertEqual((cfg["configured"], cfg["model"]), (False, "claude-sonnet-5-5"))
        self.assertEqual(self.request("PUT", "/api/ai/key", body={"key": "nao-e-chave"})[0], 400)
        self.assertEqual(self.transport.calls, [])

        status, cfg, _ = self.request("PUT", "/api/ai/key", body={"key": KEY})
        self.assertEqual(status, 200)
        self.assertTrue(cfg["configured"])
        self.assertEqual(cfg["masked"], "sk-ant-…" + KEY[-4:])
        self.assertEqual([m["id"] for m in cfg["models"]], ["claude-sonnet-5-5", "claude-opus-5"])
        self.assertEqual(self.request("PATCH", "/api/ai/config", body={"model": "claude-opus-5"})[1]["model"], "claude-opus-5")
        self.assertEqual(self.request("PATCH", "/api/ai/config", body={"model": "gpt-9"})[0], 400)

        for path in ("/api/ai/config", "/api/state"):
            self.assertNotIn(KEY, json.dumps(self.request("GET", path)[1]))
        store_files = " ".join(p.read_text(encoding="utf-8") for p in (self.tmp / "home").rglob("*.json"))
        self.assertNotIn(KEY, store_files)
        self.assertNotIn(KEY, self.log.getvalue())

        self.assertFalse(self.request("DELETE", "/api/ai/key")[1]["configured"])

    def test_chave_recusada_nao_grava(self):
        self.app.ai_transport = FakeTransport((401, {"error": {"message": "invalid x-api-key"}}))
        status, data, _ = self.request("PUT", "/api/ai/key", body={"key": KEY})
        self.assertEqual(status, 400)
        self.assertIn("recusada", data["error"])
        self.assertIsNone(self.app.keystore.get())


class DefaultKeystoreTest(TempDirTestCase):
    def test_app_usa_runner_do_app(self):
        runner = FakeRunner()
        app = VulcanApp(env={"VULCAN_TERMINAL_HOME": str(self.tmp / "h"), "VULCAN_LERD_BIN": str(self.tmp / "x"),
                             "VULCAN_VALET_BIN": str(self.tmp / "y"), "HOME": str(self.tmp)}, runner=runner).start()
        try:
            self.assertIs(app.keystore.runner, runner)  # testes nunca tocam o Keychain real
        finally:
            app.shutdown()
