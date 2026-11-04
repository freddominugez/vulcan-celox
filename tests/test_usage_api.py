"""Usage API (JSON and CSV) over the fixtures."""

import csv
import io
import shutil

from tests.helpers import FIXTURES
from tests.test_agents_api import AgentsServerCase
from vulcan_celox.core.agents import usage

USO = FIXTURES / "agents" / "usage"
USO_SID = "33333333-4444-4555-8666-777777777777"
CODEX_USO_SID = "019a1111-2222-7333-8444-555555555555"
PERIODO = "from=2026-10-29&to=2026-11-01"


class UsageServerCase(AgentsServerCase):
    def env(self):
        env = super().env()
        target = self.tmp / "claude" / "projects" / "-Users-dev-loja" / f"{USO_SID}.jsonl"
        if not target.exists():
            shutil.copy(USO / "claude-uso.jsonl", target)
            day = self.tmp / "codex" / "sessions" / "2026" / "10" / "30"
            day.mkdir(parents=True, exist_ok=True)
            shutil.copy(USO / f"rollout-2026-10-30T20-00-00-{CODEX_USO_SID}.jsonl", day)
        return env


class UsageApiTest(UsageServerCase):
    def test_agrupamentos_e_total(self):
        for group in usage.GROUPS:
            data = self.get(f"/api/agents/usage?{PERIODO}&group={group}")
            self.assertEqual(data["group"], group)
            self.assertTrue(data["groups"], group)
            total = data["total"]
            self.assertEqual(sum(g["total_tokens"] for g in data["groups"]), total["total_tokens"], group)
            for k in usage.TOKEN_FIELDS:
                self.assertEqual(sum(g["tokens"][k] for g in data["groups"]), total["tokens"][k], (group, k))
            costs = [g["cost"] for g in data["groups"] if g["cost"] is not None]
            self.assertAlmostEqual(sum(costs), total["cost"], places=4)
            self.assertIn("preço da API", data["estimate_note"])
        agents = {g["key"] for g in self.get(f"/api/agents/usage?{PERIODO}&group=agent")["groups"]}
        self.assertEqual(agents, {"claude", "codex"})
        sessions = {g["key"]: g for g in self.get(f"/api/agents/usage?{PERIODO}&group=session")["groups"]}
        self.assertIn(USO_SID, sessions)
        self.assertEqual(sessions[USO_SID]["project"], "loja")

    def test_custo_bate_com_a_tabela(self):
        models = {g["key"]: g for g in self.get(f"/api/agents/usage?{PERIODO}&group=model")["groups"]}
        sonnet = models["claude-sonnet-5-5"]  # msg_C of the usage fixture: 10 in, 50 out, 6700 read, 300 5m write
        expected = (10 * 2 + 50 * 10 + 6700 * 0.10 + 300 * 2.5) / 1_000_000
        self.assertAlmostEqual(sonnet["cost"], expected, places=9)
        self.assertIsNone(models["gpt-5.5-codex"]["cost"])  # model without a verified price: null, never 0

    def test_periodo_padrao_e_filtro(self):
        data = self.get("/api/agents/usage?from=2026-10-31&to=2026-10-31&group=day")
        self.assertTrue(all(g["key"] == "2026-10-31" for g in data["groups"]))
        self.assertEqual(self.get("/api/agents/usage")["group"], "day")

    def test_parametro_invalido_400_e_sem_token_401(self):
        for q in ("group=semana", "from=ontem", "to=2026-13-01", "from=2026-10-31&to=2026-10-01",
                  "from=2020-01-01&to=2026-10-31"):
            status, data, _ = self.request("GET", f"/api/agents/usage?{q}")
            self.assertEqual(status, 400, q)
        status, _, _ = self.request("GET", "/api/agents/usage", token=False)
        self.assertEqual(status, 401)


class SessionCostTest(UsageServerCase):
    def test_sessao_traz_o_custo_estimado(self):
        cost = self.get(f"/api/agents/sessions/{USO_SID}")["session"]["cost"]
        self.assertEqual(cost["turns"], 3)
        self.assertFalse(cost["partial"])
        self.assertGreater(cost["value"], 0)
        codex = self.get(f"/api/agents/sessions/{CODEX_USO_SID}")["session"]["cost"]
        self.assertIsNone(codex["value"])  # gpt-5.5-codex has no verified price


class UsageCsvTest(UsageServerCase):
    def csv_rows(self, query):
        status, body, headers = self.request("GET", f"/api/agents/usage.csv?{query}")
        self.assertEqual(status, 200)
        text = body if isinstance(body, str) else body.decode("utf-8") if isinstance(body, bytes) else str(body)
        return list(csv.reader(io.StringIO(text))), headers

    def test_csv_tem_cabecalho_fixo_e_os_mesmos_numeros(self):
        for group in usage.GROUPS:
            rows, _ = self.csv_rows(f"{PERIODO}&group={group}")
            self.assertEqual(tuple(rows[0]), usage.CSV_HEADER)
            data = self.get(f"/api/agents/usage?{PERIODO}&group={group}")
            self.assertEqual(len(rows) - 1, len(data["groups"]))
            for line, g in zip(rows[1:], data["groups"]):
                rec = dict(zip(usage.CSV_HEADER, line))
                self.assertEqual(rec["chave"], g["key"])
                self.assertEqual(int(rec["total_tokens"]), g["total_tokens"])
                self.assertEqual(int(rec["cache_read"]), g["tokens"]["cache_read"])
                if g["cost"] is None:
                    self.assertEqual(rec["custo_usd"], "")
                else:
                    self.assertAlmostEqual(float(rec["custo_usd"]), g["cost"], places=6)

    def test_csv_sem_texto_livre(self):
        rows, _ = self.csv_rows(f"{PERIODO}&group=session")
        text = "\n".join(",".join(r) for r in rows)
        for free in ("corrija o checkout", "continue", "rode os testes", "API Error"):
            self.assertNotIn(free, text)
        numeric = usage.CSV_HEADER[4:13]
        for line in rows[1:]:
            rec = dict(zip(usage.CSV_HEADER, line))
            for k in numeric:
                if rec[k]:
                    float(rec[k])

    def test_csv_exige_token_e_valida(self):
        status, _, _ = self.request("GET", f"/api/agents/usage.csv?{PERIODO}", token=False)
        self.assertEqual(status, 401)
        status, _, _ = self.request("GET", "/api/agents/usage.csv?group=x")
        self.assertEqual(status, 400)


class DoctorUsageTest(UsageServerCase):
    def test_doctor_mostra_tokens_e_custo_por_agente(self):
        from datetime import date
        from unittest import mock
        with mock.patch.object(usage, "period", return_value=(date(2026, 10, 2), date(2026, 10, 31))):
            out = usage.doctor_summary(self.app.data_dir)
        self.assertEqual(set(out["agentes"]), {"claude", "codex"})
        self.assertGreater(out["total"]["tokens"], 0)
        self.assertIn("preço da API", out["nota"])
        self.assertEqual(usage.doctor_summary(self.tmp / "vazio")["agentes"], {})
