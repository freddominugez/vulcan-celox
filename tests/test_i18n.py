"""English interface: every text has a translation, nothing escapes t(), and the server answers in the chosen language."""

import importlib.util
import json
import re
import unittest
from pathlib import Path

from tests.server_helpers import ServerTestCase
from vulcan_celox.core import i18n

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "vulcan_celox" / "web"
EN = json.loads((WEB / "i18n" / "en.json").read_text(encoding="utf-8"))
JS = [p for p in WEB.rglob("*.mjs") if "vendor" not in p.parts]
T = re.compile(r"""\bt\(\s*"((?:[^"\\]|\\.)*)\"""")
# tr() and HttpError with literal text; the f-string becomes {nome} in the dictionary
SERVER = re.compile(r"""(?:\btr\(\s*|HttpError\(\d+,\s*)(f?)"((?:[^"\\]|\\.)*)\"""")


def web_keys():
    keys = set()
    for path in JS:
        keys |= {json.loads(f'"{m}"') for m in T.findall(path.read_text(encoding="utf-8"))}
    keys |= set(re.findall(r'data-i18n(?:-[a-z-]+)?="([^"]+)"', (WEB / "index.html").read_text(encoding="utf-8")))
    return keys


class DicionarioTest(unittest.TestCase):
    def test_todo_texto_da_interface_tem_traducao(self):
        self.assertEqual(sorted(web_keys() - set(EN)), [])

    def test_todo_texto_do_servidor_tem_traducao(self):
        missing = []
        for folder in ("server", "core"):
            for path in (ROOT / "vulcan_celox" / folder).rglob("*.py"):
                for is_f, text in SERVER.findall(path.read_text(encoding="utf-8")):
                    text = json.loads(f'"{text}"')
                    if is_f:
                        text = re.sub(r"\{([^{}]*)\}", lambda m: "{" + re.sub(r"\W+", "_", m.group(1)).strip("_") + "}", text)
                    if text not in EN and not any(re.sub(r"\{\w+\}", "{}", k) == re.sub(r"\{\w+\}", "{}", text) for k in EN if "{" in k):
                        missing.append(f"{path.name}: {text[:70]}")
        self.assertEqual(sorted(missing), [])

    def test_mesmos_marcadores(self):
        bad = [k for k, v in EN.items() if set(re.findall(r"\{\w+\}", k)) != set(re.findall(r"\{\w+\}", v))]
        self.assertEqual(bad, [])

    def test_ingles_nao_tem_portugues_nem_travessao(self):
        self.assertEqual([v for v in EN.values() if re.search(r"[ãõçáéíóúâêô]", v) and "Português" not in v], [])

    def test_ajuda_tem_a_mesma_estrutura(self):
        pt = json.loads((WEB / "help" / "conteudo.json").read_text(encoding="utf-8"))
        en = json.loads((WEB / "help" / "conteudo.en.json").read_text(encoding="utf-8"))
        self.assertEqual([s["id"] for s in pt["secoes"]], [s["id"] for s in en["secoes"]])
        self.assertEqual(len(pt["faq"]), len(en["faq"]))
        for a, b in zip(pt["secoes"], en["secoes"]):
            self.assertEqual([list(x) for x in a["blocos"]], [list(x) for x in b["blocos"]], a["id"])


class SemTextoSoltoTest(unittest.TestCase):
    def test_nada_escapa_do_t(self):
        """scripts/i18n_restos.py points out classes, selectors and comments; the frozen list is those false alarms."""
        spec = importlib.util.spec_from_file_location("restos", ROOT / "scripts" / "i18n_restos.py")
        restos = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(restos)
        antigos = json.loads((ROOT / "tests" / "i18n_falsos_alarmes.json").read_text(encoding="utf-8"))
        for path in [*JS, WEB / "index.html"]:
            if path.name in restos.FORA:
                continue
            with self.subTest(arquivo=path.name):
                self.assertLessEqual(len(restos.restos(path)), antigos.get(path.name, 0))


class TrTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("pt")

    def test_ingles_traduz_e_portugues_nao(self):
        key = next(k for k in EN if "{" not in k)
        self.assertEqual(i18n.tr(key), key)
        i18n.set_language("en")
        self.assertEqual(i18n.tr(key), EN[key])

    def test_reconhece_texto_ja_preenchido(self):
        i18n.set_language("en")
        key = next(k for k in EN if re.fullmatch(r"[^{}]*\{\w+\}[^{}]+", k) and "{" not in EN[k].replace("{" + re.search(r"\{(\w+)\}", k).group(1) + "}", ""))
        name = re.search(r"\{(\w+)\}", key).group(1)
        self.assertEqual(i18n.tr(key.replace("{" + name + "}", "XYZ")), EN[key].replace("{" + name + "}", "XYZ"))

    def test_texto_desconhecido_passa_igual(self):
        i18n.set_language("en")
        self.assertEqual(i18n.tr("nunca visto"), "nunca visto")

    def test_escolha(self):
        i18n.DEFAULT = "en"
        self.addCleanup(setattr, i18n, "DEFAULT", "pt")
        self.assertEqual(i18n.resolve({}, {}), "en")
        self.assertEqual(i18n.resolve({"language": "pt"}, {}), "pt")
        self.assertEqual(i18n.resolve({"language": "pt"}, {"VULCAN_LANGUAGE": "en"}), "en")
        self.assertEqual(i18n.resolve({"language": "xx"}, {}), "en")


class EmIngles(ServerTestCase):
    def env(self):
        env = super().env()
        env.pop("VULCAN_LANGUAGE")
        return env

    def setUp(self):
        i18n.DEFAULT = "en"
        super().setUp()

    def tearDown(self):
        super().tearDown()
        i18n.DEFAULT = "pt"
        i18n.set_language("pt")

    def test_ingles_e_o_padrao_e_escolha_fica(self):
        data = self.request("GET", "/api/i18n")[1]
        self.assertEqual(data["language"], "en")
        self.assertGreater(len(data["dictionary"]), 1000)
        self.assertEqual(self.request("PATCH", "/api/preferences", {"language": "pt"})[1]["language"], "pt")
        self.assertEqual(self.request("GET", "/api/i18n")[1], {"language": "pt", "dictionary": {}})
        self.assertEqual(self.request("PATCH", "/api/preferences", {"language": "xx"})[0], 400)

    def test_erro_da_api_em_ingles(self):
        status, data, _ = self.request("POST", "/api/open", {"kind": "nada"})
        self.assertEqual(status, 400)
        self.assertNotRegex(data["error"], r"deve ser")

    def test_exige_token(self):
        self.assertEqual(self.request("GET", "/api/i18n", token=False)[0], 401)
