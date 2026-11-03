import unittest

from tests.helpers import FIXTURES
from vulcan_celox.core.miniyaml import MiniYamlError, loads


class MiniYamlTest(unittest.TestCase):
    def test_sites_do_lerd(self):
        data = loads((FIXTURES / "lerd-sites.yaml").read_text(encoding="utf-8"))
        sites = data["sites"]
        self.assertEqual(len(sites), 3)
        demo, loja, legado = sites
        self.assertEqual(demo["name"], "vulcan-demo")
        self.assertEqual(demo["domains"], ["vulcan-demo.test"])
        self.assertEqual(demo["php_version"], "8.5")
        self.assertIs(demo["secured"], False)
        self.assertEqual(demo["public_dir"], "public")
        self.assertEqual(loja["domains"], ["loja.test", "admin.loja.test"])
        self.assertIs(loja["secured"], True)
        self.assertEqual((loja["worker_ports"], loja["paused_workers"]), ({}, []))
        self.assertEqual(legado["domain"], "legado.test")
        self.assertEqual(legado["path"], "/Users/dev/Code/sistema legado")
        self.assertEqual(legado["node_version"], "")

    def test_config_do_lerd(self):
        data = loads((FIXTURES / "lerd-config.yaml").read_text(encoding="utf-8"))
        self.assertEqual(data["dns"], {"enabled": True, "tld": "test"})
        self.assertEqual(data["parked_directories"], ["/Users/dev/Lerd"])
        self.assertEqual(data["nginx"]["http_port"], 80)
        self.assertEqual(data["services"]["mailpit"]["image"], "docker.io/axllent/mailpit:latest")
        self.assertEqual(data["php"]["xdebug_enabled"], {})

    def test_escalares_e_comentarios(self):
        data = loads("a: 'it''s' # comentário\nb: \"x # não é comentário\"\nc: ~\nd: [1, dois]\ne: -3\n")
        self.assertEqual(data, {"a": "it's", "b": "x # não é comentário", "c": None, "d": [1, "dois"], "e": -3})

    def test_lista_no_mesmo_nivel_da_chave(self):
        self.assertEqual(loads("itens:\n- a\n- b\noutro: 1\n"), {"itens": ["a", "b"], "outro": 1})

    def test_lista_de_mapas_aninhada(self):
        text = "grupos:\n  - nome: x\n    membros:\n      - nome: y\n        idade: 3\n  - nome: z\n"
        self.assertEqual(loads(text), {"grupos": [{"nome": "x", "membros": [{"nome": "y", "idade": 3}]},
                                                  {"nome": "z"}]})

    def test_vazio(self):
        self.assertIsNone(loads("# só comentário\n\n"))

    def test_indentacao_quebrada(self):
        with self.assertRaises(MiniYamlError) as ctx:
            loads("sites:\n    - name: a\n      path: /x\n        php: 8\n")
        self.assertEqual(ctx.exception.line, 4)
        with self.assertRaises(MiniYamlError) as ctx:
            loads("a: 1\n\tb: 2\n")
        self.assertEqual(ctx.exception.line, 2)
        with self.assertRaises(MiniYamlError):
            loads("so texto sem chave\n")
