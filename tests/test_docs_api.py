"""A referência da API (docs/en e docs/pt-BR) lista exatamente as rotas declaradas em vulcan_terminal/server/."""
import re
import unittest
from pathlib import Path

from tests.server_helpers import ServerTestCase

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "vulcan_terminal" / "server"
DOCS = (ROOT / "docs" / "en" / "http-api.md", ROOT / "docs" / "pt-BR" / "http-api.md")

# @srv.route("GET", r"/api/...") e o @route(...) local do caderno; srv.route(method, pattern) não casa
ROUTE = re.compile(r'\broute\(\s*"(GET|POST|PUT|PATCH|DELETE)",\s*(?:rf|fr|r|f)?"([^"]+)"')
WEBSOCKET = re.compile(r'\.websocket\(\s*(?:rf|fr|r|f)?"([^"]+)"')
# constantes interpoladas nos padrões f-string
CONSTANTS = {"{SESSION_ID}": "<sid>", "{NAME_RE}": "<name>", "{SITE_NAME}": "<name>", "{site_name}": "<name>"}
GROUP = re.compile(r"\(\?P<(\w+)>[^)]*\)")
DOC_ROW = re.compile(r"^\|\s*(GET|POST|PUT|PATCH|DELETE|WS)\s*\|\s*`([^`]+)`", re.M)


def readable(pattern):
    """Padrão de rota na forma usada na documentação: /api/sites/(?P<name>...) vira /api/sites/<name>."""
    for constant, name in CONSTANTS.items():
        pattern = pattern.replace(constant, name)
    return GROUP.sub(r"<\1>", pattern).replace("\\.", ".")


def routes_in_code():
    found = set()
    for path in SERVER.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        found |= {(method, readable(pattern)) for method, pattern in ROUTE.findall(text)}
        found |= {("WS", readable(pattern)) for pattern in WEBSOCKET.findall(text)}
    return found


def routes_in_doc(path):
    return set(DOC_ROW.findall(path.read_text(encoding="utf-8")))


class DocsApiTest(unittest.TestCase):
    def test_doc_lista_as_rotas_do_codigo(self):
        code = routes_in_code()
        self.assertGreater(len(code), 100)
        for doc in DOCS:
            listed = routes_in_doc(doc)
            self.assertEqual(sorted(code - listed), [], f"rotas do código fora de {doc.name} ({doc.parent.name})")
            self.assertEqual(sorted(listed - code), [], f"rotas em {doc.name} ({doc.parent.name}) que não existem")


class RegexCobreOServidorTest(ServerTestCase):
    def test_regex_acha_o_que_o_servidor_registra(self):
        srv = self.app.server
        live = {(method, readable(pattern.pattern[1:-1])) for method, pattern, _fn in srv.routes}
        live |= {("WS", readable(pattern.pattern[1:-1])) for pattern, _fn in srv.ws_routes}
        self.assertEqual(sorted(live ^ routes_in_code()), [])


if __name__ == "__main__":
    unittest.main()
