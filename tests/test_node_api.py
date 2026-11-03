"""Lista de projetos Node, detalhe e sugestões vindas das sessões dos agentes."""

import json
import shutil

from tests.helpers import FIXTURES
from tests.server_helpers import ServerTestCase
from tests.test_agents_api import AgentsServerCase

N = FIXTURES / "node"


class NodeApiTest(ServerTestCase):
    def setUp(self):
        super().setUp()
        shutil.copytree(N / "painel", self.tmp / "painel")
        (self.tmp / "sem-node").mkdir()

    def call(self, method, path, body=None, expect=200):
        status, data, _ = self.request(method, path, body)
        self.assertEqual(status, expect, data)
        return data

    def test_adicionar_detalhar_e_remover(self):
        added = self.call("POST", "/api/node-projects", {"path": str(self.tmp / "painel")})
        self.assertEqual((added["name"], added["framework"], added["gerenciador"]), ("painel", "Next.js", "pnpm"))
        self.assertTrue(added["supabase"] and added["vercel"])
        lista = self.call("GET", "/api/node-projects")["projects"]
        self.assertEqual([p["name"] for p in lista], ["painel"])
        info = self.call("GET", "/api/node-projects/painel")
        self.assertEqual((info["estado"], info["porta_provavel"]), ("ok", 3100))
        self.call("POST", "/api/node-projects/painel/remove", {})
        self.assertEqual(self.call("GET", "/api/node-projects")["projects"], [])
        self.assertTrue((self.tmp / "painel" / "package.json").is_file())  # nada saiu do disco

    def test_dois_cadastros_ao_mesmo_tempo_nao_perdem_projeto(self):
        """Ler, mudar e salvar a lista ficam sob a mesma trava."""
        import threading
        for name in ("um", "dois", "tres", "quatro"):
            shutil.copytree(N / "painel", self.tmp / name)
        results = []
        threads = [threading.Thread(target=lambda n=n: results.append(
            self.request("POST", "/api/node-projects", {"path": str(self.tmp / n)})[0]))
            for n in ("um", "dois", "tres", "quatro")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results, [200] * 4)
        names = sorted(p["name"] for p in self.call("GET", "/api/node-projects")["projects"])
        self.assertEqual(names, ["dois", "quatro", "tres", "um"])

    def test_erros(self):
        self.call("POST", "/api/node-projects", {"path": str(self.tmp / "painel")})
        self.call("POST", "/api/node-projects", {"path": str(self.tmp / "painel"), "name": "outro"}, expect=409)
        self.call("POST", "/api/node-projects", {"path": str(self.tmp / "painel"), "name": "painel"}, expect=409)
        self.call("POST", "/api/node-projects", {"path": str(self.tmp / "sem-node")}, expect=400)
        self.call("POST", "/api/node-projects", {"path": "relativo/x"}, expect=400)
        self.call("POST", "/api/node-projects", {"path": str(self.tmp / "painel"), "name": "Nome Ruim"}, expect=400)
        self.call("GET", "/api/node-projects/nao-existe", expect=404)
        self.call("POST", "/api/node-projects/nao-existe/remove", {}, expect=404)
        status, _, _ = self.request("GET", "/api/node-projects", token=False)
        self.assertEqual(status, 401)


class NodeSuggestTest(AgentsServerCase):
    SID = "55555555-6666-4777-8888-999999999999"

    def env(self):
        env = super().env()
        proj = self.tmp / "app-next"
        if not proj.exists():
            shutil.copytree(N / "vite-app", proj)
            line = {"type": "user", "timestamp": "2026-10-30T10:00:00Z", "cwd": str(proj),
                    "message": {"role": "user", "content": "rode o dev"}}
            folder = self.tmp / "claude" / "projects" / "-app-next"
            folder.mkdir(parents=True)
            (folder / f"{self.SID}.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")
        return env

    def test_sugere_pasta_dos_agentes_com_package_json(self):
        got = self.get("/api/node-projects/suggest")["suggestions"]
        self.assertEqual(got, [{"path": str(self.tmp / "app-next"), "name": "app-next"}])
        status, _, _ = self.request("POST", "/api/node-projects", {"path": str(self.tmp / "app-next")})
        self.assertEqual(status, 200)
        self.assertEqual(self.get("/api/node-projects/suggest")["suggestions"], [])


class FakePty:
    def __init__(self, sid, title):
        self.id, self.title, self.alive, self.written, self.out = sid, title, True, [], b""

    def write(self, data):
        self.written.append(data)

    def history(self):
        return self.out


class FakeTerminals:
    def __init__(self):
        self.items = {}

    def get(self, sid):
        return self.items.get(sid)


class NodeRunTest(ServerTestCase):
    def setUp(self):
        super().setUp()
        for name in ("painel", "vite-app"):
            shutil.copytree(N / name, self.tmp / name)
        self.spawned = []
        self.real_terminals = self.app.terminals
        self.app.terminals = FakeTerminals()

        def spawn(cwd, title, theme, site=None, rows=30, cols=110, command=None, typed=None):
            pty = FakePty(f"{len(self.spawned) + 1:08x}", title)
            self.spawned.append((cwd, title, typed))
            self.app.terminals.items[pty.id] = pty
            return pty

        self.app.spawn_terminal = spawn
        self.app.store.save("node_projects", {"painel": str(self.tmp / "painel"), "vite": str(self.tmp / "vite-app")})

    def tearDown(self):
        self.app.terminals = self.real_terminals
        super().tearDown()

    def call(self, method, path, body=None, expect=200):
        status, data, _ = self.request(method, path, body)
        self.assertEqual(status, expect, data)
        return data

    def test_comando_digitado_por_gerenciador(self):
        vite = self.tmp / "vite-app"
        for lock, pm in (("", "npm"), ("yarn.lock", "yarn"), ("bun.lock", "bun"), ("pnpm-lock.yaml", "pnpm")):
            if lock:
                (vite / lock).write_text("x")
            got = self.call("POST", "/api/node-projects/vite/run", {"script": "dev"}, expect=201)
            self.assertEqual(got["comando"], f"{pm} run dev")
        self.assertEqual(self.spawned[0], (str(vite), "vite · dev", "npm run dev"))

    def test_script_invalido_ou_inexistente(self):
        self.call("POST", "/api/node-projects/painel/run", {"script": "deploy"}, expect=400)
        for bad in ("dev; rm -rf /", "a b", "", "$(id)"):
            self.call("POST", "/api/node-projects/painel/run", {"script": bad}, expect=400)
        self.assertEqual(self.spawned, [])

    def test_supabase(self):
        got = self.call("POST", "/api/node-projects/painel/supabase/start", {}, expect=201)
        self.assertEqual(got["comando"], "supabase start")
        self.call("POST", "/api/node-projects/painel/supabase/reset", {}, expect=400)
        self.call("POST", "/api/node-projects/vite/supabase/start", {}, expect=409)

    def test_parar_so_na_aba_do_projeto_e_url(self):
        mine = self.call("POST", "/api/node-projects/painel/run", {"script": "dev"}, expect=201)["terminal"]
        other = self.call("POST", "/api/node-projects/vite/run", {"script": "dev"}, expect=201)["terminal"]
        self.app.terminals.items[mine].out = b"\x1b[1m\xe2\x96\xb2 Next.js 16\x1b[0m\n - Local: http://localhost:3100\n"
        info = self.call("GET", "/api/node-projects/painel")
        self.assertEqual([(r["terminal"], r["url"]) for r in info["rodando"]], [(mine, "http://localhost:3100")])
        self.call("POST", "/api/node-projects/painel/stop", {"terminal": other}, expect=404)
        self.call("POST", "/api/node-projects/painel/stop", {"terminal": mine})
        self.assertEqual(self.app.terminals.items[mine].written, [b"\x03"])
        self.assertEqual(self.app.terminals.items[other].written, [])
        self.app.terminals.items[mine].alive = False
        self.assertEqual(self.call("GET", "/api/node-projects/painel")["rodando"], [])
        self.call("POST", "/api/node-projects/painel/stop", {"terminal": mine}, expect=404)
