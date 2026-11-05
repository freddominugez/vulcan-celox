"""An English message is not translated twice, and a generic key does not rewrite a sentence."""

import unittest
from unittest import mock

from vulcan_celox.core import i18n


class PadroesTest(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(i18n, "_language", "en")
        patch.start()
        self.addCleanup(patch.stop)

    def test_mensagem_ja_em_ingles_fica_igual(self):
        for text in ("this file is not a Vulcan Celox backup", "the backup has a refused path: x.txt",
                     "this backup came from a newer version of the app", "the file is damaged or is not a backup (a de b)"):
            self.assertEqual(i18n.tr(text), text)

    def test_dado_dentro_da_mensagem_nao_muda(self):
        self.assertEqual(i18n.tr("nome a outro"), "nome a outro")
        self.assertEqual(i18n.tr("1 de 3"), "1 de 3")

    def test_texto_preenchido_com_palavras_continua_traduzido(self):
        self.assertEqual(i18n.tr("PHP 8.3: quebrou"), "PHP 8.3: quebrou".replace("PHP 8.3: quebrou", i18n.dictionary()["PHP {version}: {msg}"].format(version="8.3", msg="quebrou")))

    def test_com_valores_nao_muda(self):
        self.assertEqual(i18n.tr("{from} a {to}", **{"from": "1", "to": "2"}), "1 to 2")
