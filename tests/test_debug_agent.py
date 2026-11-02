"""vt-06 C4: exceções e logs de erro do site durante a sessão de agente, com resumo mascarado."""

import json

from tests.helpers import FIXTURES, TempDirTestCase
from vulcan_terminal.core.lerd_dumps import SUMMARY_MAX, events_for_session, parse_events, session_summary, site_for_path

EVENTS = parse_events(json.loads((FIXTURES / "lerd-api-dumps.json").read_text(encoding="utf-8")))


def log(ts, level="error", message="Falhou", site="loja"):
    return parse_events([{"ts": ts, "kind": "log", "ctx": {"site": site, "request": "GET /x"},
                          "src": {"file": "/s/loja/app/X.php", "line": 7}, "data": {"level": level, "message": message}}])[0]


class JanelaTest(TempDirTestCase):
    def test_site_e_janela(self):
        events = [log("2026-10-31T10:00:00.100Z"), log("2026-10-31T10:30:00Z", site="vitrine"),
                  log("2026-10-31T09:59:00Z"), log("2026-10-31T10:20:00Z", level="info"),
                  log("2026-10-31T11:00:30Z"), log("2026-10-31T11:10:00Z")]
        found = events_for_session(events, "loja", "2026-10-31T10:00:00.000Z", "2026-10-31T11:00:00.000Z")
        # dentro da janela (com folga de um minuto no fim), só do site e só nível de erro
        self.assertEqual([e["ts"] for e in found], ["2026-10-31T10:00:00.100Z", "2026-10-31T11:00:30Z"])

    def test_fuso_diferente_e_eventos_reais(self):
        found = events_for_session(EVENTS, "loja", "2026-10-31T18:00:00-03:00", "2026-10-31T18:05:00-03:00")
        self.assertTrue(found)  # 21:01Z cai entre 21:00Z e 21:05Z
        self.assertTrue(all(e["kind"] == "log" and e["site"] == "loja" for e in found))
        self.assertEqual(events_for_session(EVENTS, "loja", "", ""), [])

    def test_resumo_mascarado_e_limitado(self):
        events = [log(f"2026-10-31T10:{i:02d}:00Z", message=f"erro {i} DB_PASSWORD=supersecreta1") for i in range(30)]
        text = session_summary(events, "loja")
        self.assertNotIn("supersecreta1", text)
        self.assertIn("[segredo]", text)
        self.assertEqual(text.count("\n- "), SUMMARY_MAX)
        self.assertIn("e mais 10", text)
        self.assertIn("app/X.php:7", text)
        self.assertNotIn("—", text)

    def test_site_pela_pasta(self):
        sites = [("loja", "/s/loja"), ("lojinha", "/s/lojinha"), ("api", "/s/loja/api")]
        self.assertEqual(site_for_path(sites, "/s/loja/app"), "loja")
        self.assertEqual(site_for_path(sites, "/s/loja/api/src"), "api")
        self.assertEqual(site_for_path(sites, "/s/lojinha"), "lojinha")
        self.assertIsNone(site_for_path(sites, "/s/outro"))
        self.assertIsNone(site_for_path(sites, ""))
