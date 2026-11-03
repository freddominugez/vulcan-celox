"""Título curto a partir do pedido colado."""
import unittest

from vulcan_celox.core.textutil import HEADLINE_MAX, headline


class HeadlineTest(unittest.TestCase):
    def test_bloco_colado_vira_a_primeira_frase(self):
        text = ("```text Execute o bloco BF (Embeddings e busca) do plano do projeto: E09, E10 com CR-12. "
                "Leia, nesta ordem: 1. contratos/README.md 2. PROTOCOLO.md ```")
        self.assertEqual(headline(text), "Execute o bloco BF (Embeddings e busca) do plano do projeto: E09, E10 com CR-12.")

    def test_quebras_de_linha_e_bloco_sem_linguagem(self):
        self.assertEqual(headline("```\ncrie o cupom\n```"), "crie o cupom")
        self.assertEqual(headline("  corrija\n  o login  "), "corrija o login")
        self.assertEqual(headline("``text\nExecute o bloco B0"), "Execute o bloco B0")  # colagem real, uma crase a menos
        self.assertEqual(headline("`npm test` falha no login"), "`npm test` falha no login")  # crase de código fica

    def test_texto_longo_sem_frase_corta_numa_palavra(self):
        out = headline("palavra " * 60)
        self.assertLessEqual(len(out), HEADLINE_MAX + 3)
        self.assertTrue(out.endswith("palavra..."))
        self.assertEqual(headline("x" * 500), "x" * HEADLINE_MAX + "...")

    def test_frase_curta_demais_nao_corta(self):
        self.assertEqual(headline("Oi. Corrija o login do painel"), "Oi. Corrija o login do painel")

    def test_vazio(self):
        for empty in (None, "", "   ", "``` ```"):
            self.assertEqual(headline(empty), "")
