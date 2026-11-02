"""vt-18 C1: temas de sessão como dados e rotação lembrada."""

from tests.helpers import TempDirTestCase
from tests.server_helpers import ServerTestCase
from vulcan_terminal.core import themes
from vulcan_terminal.core.store import Store

XTERM_KEYS = {"background", "foreground", "cursor", "selectionBackground", "black", "red", "green", "yellow", "blue",
              "magenta", "cyan", "white", "brightBlack", "brightWhite"}


class ThemesTest(TempDirTestCase):
    def test_quatro_temas_na_ordem_da_rotacao(self):
        self.assertEqual(themes.ROTATION, ["homebrew", "classico", "oceano", "ardosia"])
        for tid in themes.ROTATION:
            t = themes.THEMES[tid]
            self.assertTrue({"name", "desc", "accent", "bg", "ink", "xterm"} <= set(t), tid)
            self.assertTrue(XTERM_KEYS <= set(t["xterm"]), tid)
            self.assertEqual(t["xterm"]["background"], t["bg"])

    def test_rotacao_avanca_e_e_lembrada(self):
        store = Store(self.tmp)
        rot = themes.Rotation(store)
        self.assertEqual(rot.peek(), "homebrew")
        self.assertEqual([rot.take() for _ in range(5)], ["homebrew", "classico", "oceano", "ardosia", "homebrew"])
        self.assertEqual(themes.Rotation(Store(self.tmp)).peek(), "classico")  # outra abertura do app continua daí

    def test_css_das_classes(self):
        css = themes.css()
        for tid in themes.ROTATION:
            self.assertIn(f".t-{tid} {{", css)
        self.assertIn("--t-bg:", css)
        self.assertNotIn("—", css)

    def test_valida(self):
        self.assertTrue(themes.is_theme("oceano"))
        self.assertFalse(themes.is_theme("rosa"))
        self.assertFalse(themes.is_theme(None))


class ThemesApiTest(ServerTestCase):
    def create(self, **body):
        status, data, _ = self.request("POST", "/api/terminals", body={"cwd": str(self.tmp), **body})
        return status, data

    def tearDown(self):
        self.app.terminals.close_all()
        super().tearDown()

    def test_terminal_com_tema_automatico_explicito_e_invalido(self):
        status, first = self.create(theme="auto")
        self.assertEqual((status, first["theme"]), (201, "homebrew"))
        status, second = self.create(theme="oceano")
        self.assertEqual(second["theme"], "oceano")
        status, third = self.create(theme="auto")
        self.assertEqual(third["theme"], "classico")  # o explícito não gasta a rotação
        status, _ = self.create(theme="rosa")
        self.assertEqual(status, 400)
        status, plain = self.create()
        self.assertIsNone(plain["theme"])  # comandos rápidos seguem sem tema
        self.assertEqual(self.app.hub.sessions.get(first["id"]).theme, "homebrew")

    def test_rota_de_temas(self):
        _, first = self.create(theme="auto")
        status, data, _ = self.request("GET", "/api/themes")
        self.assertEqual(status, 200)
        self.assertEqual([t["id"] for t in data["themes"]], themes.ROTATION)
        self.assertEqual(data["next"], "classico")
        self.assertEqual(data["in_use"], {"homebrew": [first["id"]]})
        self.assertIn(".t-oceano {", data["css"])
