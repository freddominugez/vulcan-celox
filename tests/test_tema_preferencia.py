"""Preferência de tema: Sistema por padrão, lembrada, e aplicada antes dos estilos para o app não piscar."""

from pathlib import Path

from tests.server_helpers import ServerTestCase

WEB = Path(__file__).resolve().parent.parent / "vulcan_celox" / "web"


class TemaPreferenciaTest(ServerTestCase):
    def test_padrao_e_sistema(self):
        self.assertEqual(self.request("PATCH", "/api/preferences", {})[1]["theme"], "sistema")

    def test_lembrada(self):
        for value in ("claro", "escuro", "sistema"):
            self.assertEqual(self.request("PATCH", "/api/preferences", {"theme": value})[1]["theme"], value)
            self.assertEqual(self.request("PATCH", "/api/preferences", {})[1]["theme"], value)

    def test_valor_invalido(self):
        for value in ("azul", 1, None):
            self.assertEqual(self.request("PATCH", "/api/preferences", {"theme": value})[0], 400)

    def test_nao_pisca_ao_abrir(self):
        index = (WEB / "index.html").read_text(encoding="utf-8")
        self.assertLess(index.index('src="js/theme-boot.js"'), index.index('href="styles/tokens.css"'))
        self.assertNotIn(" defer", index[:index.index('href="styles/tokens.css"')])

    def test_js_nao_confunde_tema_da_pagina_com_tema_da_aba(self):
        # <html data-theme> é o tema da interface: qualquer closest("[data-theme]") acha a página inteira
        for path in (WEB / "js").rglob("*.mjs"):
            self.assertNotIn('"[data-theme]"', path.read_text(encoding="utf-8"), path.name)

