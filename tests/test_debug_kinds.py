"""vt-06 C3: queries (repetidas, tempo mínimo), logs com nível e tipos desconhecidos."""

import json

from tests.helpers import FIXTURES, TempDirTestCase
from vulcan_terminal.core.lerd_dumps import filter_min_ms, group_queries, log_tone, parse_events

EVENTS = parse_events(json.loads((FIXTURES / "lerd-api-dumps.json").read_text(encoding="utf-8")))


def query(sql, ms, rid="r1"):
    return {"kind": "query", "rid": rid, "data": {"sql": sql, "time_ms": ms}, "ts": "", "site": "loja"}


class QueriesTest(TempDirTestCase):
    def test_agrupa_identicas(self):
        events = [query("select * from users where id = ?", 10), query("select * from users where id = ?", 30),
                  query("select * from orders", 5), query("select * from users where id = ?", 20),
                  query("select * from orders", 15)]
        groups = group_queries(events)
        self.assertEqual([(g["sql"], g["count"], g["total_ms"]) for g in groups],
                         [("select * from users where id = ?", 3, 60.0), ("select * from orders", 2, 20.0)])

    def test_repetidas_nos_eventos_reais(self):
        req = [e for e in EVENTS if e["kind"] == "query" and e["request"] == "GET /vt06"]
        users = next(g for g in group_queries(req) if g["sql"] == "select * from users where id = ?")
        self.assertEqual(users["count"], 2)  # a rota de teste roda a mesma query duas vezes

    def test_tempo_minimo_so_nas_queries(self):
        events = [query("a", 80), query("b", 10), {"kind": "log", "data": {"level": "error"}}, query("c", 50)]
        kept = filter_min_ms(events, 50)
        self.assertEqual([e["data"].get("sql") for e in kept if e["kind"] == "query"], ["a", "c"])
        self.assertEqual(len([e for e in kept if e["kind"] == "log"]), 1)
        self.assertEqual(len(filter_min_ms(events, 0)), 4)


class NiveisTest(TempDirTestCase):
    def test_tom_por_nivel(self):
        self.assertEqual([log_tone(level) for level in ("error", "CRITICAL", "emergency", "warning", "notice",
                                                        "info", "debug", "estranho")],
                         ["err", "err", "err", "warn", "warn", "info", "dim", "info"])

    def test_tipo_desconhecido_vira_texto(self):
        event = parse_events([{"kind": "mail", "data": {"subject": "Bem-vindo"}, "ctx": {}}])[0]
        self.assertEqual(event["kind"], "mail")
        self.assertEqual(event["data"]["subject"], "Bem-vindo")
