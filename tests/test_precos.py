"""vt-22 C2: tabela de preços e custo estimado por turno."""

import json

from tests.helpers import TempDirTestCase
from vulcan_terminal.core.agents import pricing


def row(model, **kw):
    base = {"model": model, "input": 0, "output": 0, "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0}
    base.update(kw)
    return base


class PrecosTest(TempDirTestCase):
    def table(self):
        return pricing.load(self.tmp)[0]

    def test_custo_de_cada_tipo_de_token_bate_com_a_conta(self):
        t = self.table()
        # Claude Opus 5.5: $4 entrada, $20 saída, $0.20 leitura, $5 escrita 5m, $8 escrita 1h (por milhão)
        self.assertAlmostEqual(pricing.cost(row("claude-opus-5-5", input=1_000_000), t), 4.0)
        self.assertAlmostEqual(pricing.cost(row("claude-opus-5-5", output=500_000), t), 10.0)
        self.assertAlmostEqual(pricing.cost(row("claude-opus-5-5", cache_read=2_000_000), t), 0.40)
        self.assertAlmostEqual(pricing.cost(row("claude-opus-5-5", cache_write_5m=100_000), t), 0.50)
        self.assertAlmostEqual(pricing.cost(row("claude-opus-5-5", cache_write_1h=100_000), t), 0.80)
        r = row("claude-opus-5-5", input=2, output=250, cache_read=1000, cache_write_5m=1000, cache_write_1h=4000)
        expected = (2 * 4 + 250 * 20 + 1000 * 0.20 + 1000 * 5 + 4000 * 8) / 1_000_000
        self.assertAlmostEqual(pricing.cost(r, t), expected)

    def test_data_de_versao_e_contexto_longo(self):
        t = self.table()
        self.assertAlmostEqual(pricing.cost(row("claude-sonnet-4-5-20250929", input=1_000_000), t), 3.0)
        # gpt-6.1-sol: prompt acima de 272 mil tokens usa o preço de contexto longo
        self.assertAlmostEqual(pricing.cost(row("gpt-6.1-sol", input=100_000, output=1000), t), 0.2 + 0.01)
        self.assertAlmostEqual(pricing.cost(row("gpt-6.1-sol", input=300_000, output=1000), t), 1.2 + 0.015)

    def test_modelo_desconhecido_e_tipo_sem_preco_dao_null(self):
        t = self.table()
        self.assertIsNone(pricing.cost(row("modelo-novo", input=10), t))
        self.assertIsNone(pricing.cost(row("", input=10), t))
        self.assertIsNone(pricing.cost(row("gpt-5.5", input=10, cache_write_5m=5), t))  # página sem preço de escrita
        self.assertEqual(pricing.cost(row("gpt-5.5"), t), 0.0)  # sem tokens: custo zero de verdade

    def test_arquivo_do_usuario_vence_o_padrao(self):
        (self.tmp / "precos.json").write_text(json.dumps({"moeda": "USD", "modelos": {
            "claude-opus-5-5-20261001": {"input": 1, "output": 2, "cache_read": 0, "cache_write_5m": 0,
                                         "cache_write_1h": 0},
            "meu-modelo": {"input": 1, "output": 1}}}))
        t, warning = pricing.load(self.tmp)
        self.assertIsNone(warning)
        self.assertAlmostEqual(pricing.cost(row("claude-opus-5-5", input=1_000_000), t), 1.0)
        self.assertEqual(pricing.lookup(t, "meu-modelo")["fonte"], "usuário")
        self.assertAlmostEqual(pricing.cost(row("claude-sonnet-5-5", input=1_000_000), t), 2.0)  # resto do padrão

    def test_json_invalido_mantem_o_padrao_e_avisa_no_doctor(self):
        (self.tmp / "precos.json").write_text("{ isto não é json")
        t, warning = pricing.load(self.tmp)
        self.assertIn("JSON inválido", warning)
        self.assertEqual(t, pricing.DEFAULT)
        self.assertIn("JSON inválido", pricing.describe(self.tmp)["aviso"])
        (self.tmp / "precos.json").write_text(json.dumps({"modelos": {"claude-opus-5-5": {"input": "caro"}}}))
        t, warning = pricing.load(self.tmp)
        self.assertIn("claude-opus-5-5", warning)
        self.assertEqual(pricing.lookup(t, "claude-opus-5-5")["input"], 4)

    def test_padrao_tem_fonte_e_data(self):
        self.assertEqual(pricing.CONFERIDO_EM, "2026-11-01")
        for name, entry in pricing.DEFAULT.items():
            self.assertIn(entry["fonte"], pricing.FONTES, name)
            self.assertTrue(pricing._valid_entry(entry), name)

