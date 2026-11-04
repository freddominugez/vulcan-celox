"""Debug screen (group by request, filter, open the source in the editor)."""

import json
import os
from unittest import mock

from tests.helpers import FIXTURES, TempDirTestCase
from tests.server_helpers import ServerTestCase
from vulcan_celox.core.lerd_dumps import filter_events, group_by_request, parse_events

EVENTS = parse_events(json.loads((FIXTURES / "lerd-api-dumps.json").read_text(encoding="utf-8")))


class AgruparTest(TempDirTestCase):
    def test_por_requisicao_mais_nova_primeiro(self):
        groups = group_by_request(EVENTS)
        self.assertEqual(len(groups), 4)  # two requests on each test site
        self.assertGreaterEqual(groups[0]["ts"], groups[-1]["ts"])
        erro = next(g for g in groups if g["site"] == "loja" and "erro=1" in g["request"])
        self.assertEqual(erro["counts"]["log"], 2)
        self.assertTrue(all(e["rid"] == erro["rid"] for e in erro["events"]))
        self.assertEqual([e["ts"] for e in erro["events"]], sorted(e["ts"] for e in erro["events"]))

    def test_filtro_combinado(self):
        found = filter_events(EVENTS, site="loja", kind="query", q="SESSIONS")
        self.assertTrue(found)
        self.assertTrue(all(e["site"] == "loja" and e["kind"] == "query" and "sessions" in e["data"]["sql"] for e in found))
        self.assertEqual(filter_events(EVENTS, site="vitrine", kind="query"), [])
        self.assertEqual(len(filter_events(EVENTS)), len(EVENTS))


class AbrirOrigemTest(ServerTestCase):
    def env(self):
        env = super().env()
        lerd = self.tmp / "bin" / "lerd"
        lerd.parent.mkdir(parents=True, exist_ok=True)
        lerd.write_text("#!/bin/sh\nexit 0\n")
        os.chmod(lerd, 0o755)
        env["VULCAN_LERD_BIN"] = str(lerd)
        return env

    def setUp(self):
        super().setUp()
        self.pasta = self.tmp / "loja"
        (self.pasta / "routes").mkdir(parents=True)
        (self.pasta / "routes" / "web.php").write_text("<?php")
        row = {"name": "loja", "domain": "loja.test", "path": str(self.pasta)}
        self.patch = mock.patch.object(self.app.backend, "api_get", side_effect=lambda p, **k: [row] if p == "/api/sites" else {})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        super().tearDown()

    def test_so_arquivo_dentro_de_um_site(self):
        status, data, _ = self.request("POST", "/api/open", body={"kind": "source", "target": str(self.pasta / "routes" / "web.php")})
        self.assertEqual(status, 200, data)
        self.assertTrue(self.fake.calls[-1].argv[-1].endswith(os.path.join("routes", "web.php")))
        fora = self.tmp / "fora.php"
        fora.write_text("<?php")
        for target in (str(fora), str(self.pasta / "routes" / "nao-existe.php"), str(self.pasta / "routes" / ".." / ".." / "fora.php")):
            with self.subTest(target=target):
                self.assertEqual(self.request("POST", "/api/open", body={"kind": "source", "target": target})[0], 400)
