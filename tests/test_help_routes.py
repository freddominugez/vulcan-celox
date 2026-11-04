"""Every sidebar route has a Help section, and every mapped section exists in the content."""

import json
import re
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "vulcan_celox" / "web"


def nav_ids():
    src = (WEB / "js" / "app-state.mjs").read_text(encoding="utf-8")
    ids = []
    for block in ("NAV", "AGENT_NAV", "HELP_NAV"):
        body = re.search(rf"const {block} = \[(.*?)\n\];", src, re.S).group(1)
        for item in re.finditer(r'\{ id: "([^"]+)"([^}]*)\}', body):
            ids.append(item.group(1))
            routes = re.search(r"routes: \[([^\]]*)\]", item.group(2))
            ids += re.findall(r'"([^"]+)"', routes.group(1) if routes else "")
    return ids


def route_map():
    src = (WEB / "js" / "help-content.mjs").read_text(encoding="utf-8")
    body = re.search(r"export const ROUTE_SECTION = \{(.*?)\n\};", src, re.S).group(1)
    return dict(re.findall(r'"?([a-z-]+)"?: "([a-z-]+)"', body))


class HelpRoutesTest(unittest.TestCase):
    def test_toda_rota_da_barra_tem_secao(self):
        ids = nav_ids()
        self.assertIn("ajuda", ids)
        self.assertIn("node-projeto", ids)
        mapping = route_map()
        sections = {s["id"] for s in json.loads((WEB / "help" / "conteudo.json").read_text(encoding="utf-8"))["secoes"]}
        missing = [i for i in ids if i not in mapping]
        self.assertEqual(missing, [], "rotas da barra lateral sem seção na Ajuda")
        self.assertEqual([v for v in mapping.values() if v not in sections], [])
