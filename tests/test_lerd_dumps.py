"""vt-06 C1: cliente da ponte de dumps do Lerd (D-015: API com X-Lerd-CSRF).

`lerd-api-dumps.json` são eventos reais do Lerd 1.37.1 gravados em 2026-10-31 (um site PHP simples e um Laravel 13
de teste, depois desfeitos), anonimizados: dump, request, query, log e view.
"""

import http.server
import json
import os
import threading
from urllib.parse import parse_qs, urlsplit

from tests.helpers import FIXTURES, TempDirTestCase
from tests.server_helpers import ServerTestCase
from vulcan_terminal.core.lerd_dumps import parse_event, parse_events

EVENTS = json.loads((FIXTURES / "lerd-api-dumps.json").read_text(encoding="utf-8"))


class ParserTest(TempDirTestCase):
    def test_eventos_reais(self):
        events = parse_events(EVENTS)
        kinds = {e["kind"] for e in events}
        self.assertEqual(kinds, {"dump", "request", "query", "log", "view"})
        dump = next(e for e in events if e["kind"] == "dump")
        self.assertEqual((dump["site"], dump["request"], dump["line"]), ("vitrine", "GET /", 2))
        self.assertIn("pedido", dump["text"])
        query = next(e for e in events if e["kind"] == "query")
        self.assertIn("select", query["data"]["sql"])
        log = next(e for e in events if e["kind"] == "log" and "Falha" in e["data"]["message"])
        self.assertEqual(log["data"]["level"], "error")

    def test_campos_a_mais_e_a_menos(self):
        event = parse_event({"v": 2, "id": "x", "kind": "novo", "campo_novo": [1, 2], "ctx": "nao e objeto"})
        self.assertEqual((event["kind"], event["site"], event["file"], event["line"]), ("novo", "", "", 0))
        self.assertIsNone(parse_event("lixo"))
        self.assertEqual(parse_events({"nao": "lista"}), [])


class LerdFalso(http.server.BaseHTTPRequestHandler):
    state = {"enabled": False, "cleared": 0, "queries": []}

    def log_message(self, *a):
        pass

    def reply(self, code, body=None):
        raw = json.dumps(body).encode() if body is not None else b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        parts = urlsplit(self.path)
        if parts.path == "/api/dumps":
            q = parse_qs(parts.query)
            self.state["queries"].append(q)
            site = (q.get("site") or [None])[0]
            kind = (q.get("kind") or [None])[0]
            self.reply(200, [e for e in EVENTS if (not site or e["ctx"]["site"] == site) and (not kind or e["kind"] == kind)])
        elif parts.path == "/api/dumps/status":
            self.reply(200, {"enabled": self.state["enabled"], "count": len(EVENTS), "capacity": 5000,
                             "addr": "tcp:127.0.0.1:9913"})
        else:
            self.reply(200, [])

    def do_POST(self):
        if self.headers.get("X-Lerd-CSRF") != "1":  # como o Lerd 1.37.1
            return self.reply(403, {"error": "cross-origin request blocked"})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if self.path == "/api/dumps/toggle":
            self.state["enabled"] = bool(body.get("enable"))
            return self.reply(200, {"enabled": self.state["enabled"]})
        if self.path == "/api/dumps/clear":
            self.state["cleared"] += 1
            return self.reply(204)
        return self.reply(404)


class ApiTest(ServerTestCase):
    def env(self):
        self.lerd_srv = http.server.HTTPServer(("127.0.0.1", 0), LerdFalso)
        threading.Thread(target=self.lerd_srv.serve_forever, daemon=True).start()
        LerdFalso.state.update(enabled=False, cleared=0, queries=[])
        env = super().env()
        lerd = self.tmp / "bin" / "lerd"
        lerd.parent.mkdir(parents=True, exist_ok=True)
        lerd.write_text("#!/bin/sh\nexit 0\n")
        os.chmod(lerd, 0o755)
        env.update({"VULCAN_LERD_BIN": str(lerd), "VULCAN_LERD_API": f"http://127.0.0.1:{self.lerd_srv.server_port}"})
        return env

    def tearDown(self):
        super().tearDown()
        self.lerd_srv.shutdown()
        self.lerd_srv.server_close()

    def test_eventos_com_filtros(self):
        data = self.request("GET", "/api/debug/events?site=loja&kind=query&q=SESSIONS")[1]
        self.assertTrue(data["events"])
        self.assertTrue(all(e["kind"] == "query" and "sessions" in e["data"]["sql"] for e in data["events"]))
        sent = LerdFalso.state["queries"][-1]
        self.assertEqual((sent["site"], sent["kind"]), (["loja"], ["query"]))
        self.assertNotIn("q", sent)  # a API do Lerd ignora busca de texto: o app filtra

    def test_ponte_liga_desliga_e_limpa_com_o_cabecalho(self):
        self.assertFalse(self.request("GET", "/api/debug/bridge")[1]["enabled"])
        self.assertTrue(self.request("PUT", "/api/debug/bridge", body={"enabled": True})[1]["enabled"])
        self.assertTrue(LerdFalso.state["enabled"])
        self.assertEqual(self.request("POST", "/api/debug/clear")[0], 200)
        self.assertEqual(LerdFalso.state["cleared"], 1)
        self.assertEqual(self.request("PUT", "/api/debug/bridge", body={"enabled": "sim"})[0], 400)


class SemLerdTest(ServerTestCase):
    def test_409(self):
        self.assertEqual(self.request("GET", "/api/debug/events")[0], 409)
        self.assertEqual(self.request("GET", "/api/debug/bridge")[0], 409)
