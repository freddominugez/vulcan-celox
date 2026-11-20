"""The three product locales share catalogs, aliases, help and API validation."""

import json
import re
import unittest
from pathlib import Path

from tests.server_helpers import ServerTestCase
from vulcan_celox.core import i18n

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "vulcan_celox/web"


class LocaleTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("pt")

    def test_aliases(self):
        for alias, expected in (("en-US", "en"), ("pt-BR", "pt"), ("es-ES", "es"), ("EN_us", "en")):
            with self.subTest(alias=alias):
                self.assertEqual(i18n.resolve({"language": alias}, {}), expected)

    def test_forma_errada_nao_impede_partida(self):
        for prefs in ([], None, "en", 2):
            self.assertEqual(i18n.resolve(prefs, {}), i18n.DEFAULT)

    def test_espanhol_e_cache_independente(self):
        for locale, expected in (("es-ES", "Configuración"), ("en-US", "Settings"), ("pt-BR", "Configurações"), ("es", "Configuración")):
            i18n.set_language(locale)
            self.assertEqual(i18n.tr("Configurações"), expected)

    def test_catalogo_es_completo_com_mesmos_marcadores(self):
        en = json.loads((WEB / "i18n/en.json").read_text())
        es = json.loads((WEB / "i18n/es.json").read_text())
        self.assertEqual(set(es), set(en))
        for key, value in es.items():
            with self.subTest(key=key[:70]):
                self.assertTrue(isinstance(value, str) and value.strip())
                self.assertEqual(sorted(re.findall(r"\{\w+\}", key)), sorted(re.findall(r"\{\w+\}", value)))
                self.assertNotIn("—", value)

    def test_ajuda_es_mesma_estrutura(self):
        en = json.loads((WEB / "help/conteudo.en.json").read_text())
        es = json.loads((WEB / "help/conteudo.es.json").read_text())
        self.assertEqual([s["id"] for s in es["secoes"]], [s["id"] for s in en["secoes"]])
        self.assertEqual(len(es["faq"]), len(en["faq"]))
        for a, b in zip(en["secoes"], es["secoes"]):
            self.assertEqual([list(x) for x in a["blocos"]], [list(x) for x in b["blocos"]])

    def test_mascara_es_sobrevive_troca_de_idioma(self):
        from vulcan_celox.core.redact import masked_count, redact
        i18n.set_language("es")
        masked, count = redact("API_KEY=" + "example-" * 3)
        self.assertEqual((masked, count), ("API_KEY=[secreto]", 1))
        i18n.set_language("en")
        self.assertEqual(redact(masked), (masked, 0))
        self.assertEqual(masked_count(masked), 1)


class ThreeLanguageApiTest(ServerTestCase):
    def env(self):
        env = super().env()
        env.pop("VULCAN_LANGUAGE")
        return env

    def test_espanhol_aceito_com_alias_e_traduz(self):
        self.assertEqual(self.request("PATCH", "/api/preferences", {"language": "es-ES"})[0], 200)
        result = self.request("GET", "/api/i18n")[1]
        self.assertEqual(result["language"], "es")
        self.assertEqual(result["dictionary"]["Configurações"], "Configuración")

    def test_idioma_invalido_nao_salva_tema_parcialmente(self):
        self.request("PATCH", "/api/preferences", {"theme": "claro"})
        self.assertEqual(self.request("PATCH", "/api/preferences", {"theme": "escuro", "language": "fr"})[0], 400)
        self.assertEqual(self.request("PATCH", "/api/preferences", {})[1]["theme"], "claro")
