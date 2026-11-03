"""Leitor de projeto Node, só leitura e sem abrir.env."""

import builtins
import os
import shutil
from unittest import mock

from tests.helpers import FIXTURES, TempDirTestCase
from vulcan_terminal.core import node_project

N = FIXTURES / "node"


class NodeProjectReaderTest(TempDirTestCase):
    def copy(self, name):
        dst = self.tmp / name
        shutil.copytree(N / name, dst)
        return dst

    def test_next_com_pnpm_supabase_e_vercel(self):
        info = node_project.read(self.copy("painel"))
        self.assertEqual(info["estado"], "ok")
        self.assertEqual(info["nome"], "painel-clientes")
        self.assertEqual(info["gerenciador"], "pnpm")
        self.assertEqual(info["framework"]["nome"], "Next.js")
        self.assertEqual(info["porta_provavel"], 3100)
        self.assertEqual(info["node"], {"valor": "24.11.0", "fonte": ".nvmrc"})
        self.assertEqual([s["nome"] for s in info["scripts"]], ["dev", "build", "start", "lint"])
        self.assertEqual(info["supabase"]["project_id"], "painel-clientes")
        self.assertEqual(info["supabase"]["porta_api"], 54321)
        self.assertEqual(info["vercel"], {"estado": "ok", "projectId": "prj_exemplo123", "orgId": "team_exemplo456"})

    def test_vite_com_npm_sem_lockfile(self):
        info = node_project.read(self.copy("vite-app"))
        self.assertEqual((info["gerenciador"], info["framework"]["nome"], info["porta_provavel"]), ("npm", "Vite", 5173))
        self.assertIsNone(info["supabase"])
        self.assertIsNone(info["vercel"])
        self.assertIsNone(info["node"])

    def test_package_json_corrompido(self):
        info = node_project.read(self.copy("quebrado"))
        self.assertEqual(info["estado"], "ilegivel")
        self.assertIn("JSON inválido", info["erro"])

    def test_pasta_sem_package_json(self):
        self.assertEqual(node_project.read(self.tmp)["estado"], "nenhum")

    def test_lockfiles(self):
        root = self.copy("vite-app")
        for lock, pm in (("package-lock.json", "npm"), ("yarn.lock", "yarn"), ("bun.lock", "bun"), ("pnpm-lock.yaml", "pnpm")):
            (root / lock).write_text("x")
            self.assertEqual(node_project.manager(root), pm)

    def test_env_nunca_e_aberto(self):
        root = self.copy("painel")
        env = root / ".env"
        env.write_text("SUPABASE_SERVICE_ROLE_KEY=segredo\n")
        os.chmod(env, 0)
        real_open = builtins.open
        opened = []

        def spy(path, *args, **kwargs):
            opened.append(str(path))
            return real_open(path, *args, **kwargs)

        try:
            with mock.patch("builtins.open", spy):
                info = node_project.read(root)
        finally:
            os.chmod(env, 0o600)
        self.assertEqual(info["estado"], "ok")
        self.assertFalse([p for p in opened if os.path.basename(p).startswith(".env")])
        self.assertNotIn("segredo", repr(info))

    def test_porta_pelo_flag_do_script(self):
        scripts = {"dev": "vite --port 4000"}
        self.assertEqual(node_project.probable_port(scripts, None), 4000)
        self.assertEqual(node_project.probable_port({"dev": "next dev -p3005"}, None), 3005)
        self.assertIsNone(node_project.probable_port({"dev": "node server.js"}, None))

    def test_comando_de_script(self):
        self.assertEqual(node_project.run_command("pnpm", "dev"), "pnpm run dev")
        self.assertEqual(node_project.run_command("bun", "db:migrate"), "bun run db:migrate")
        for bad in ("dev; rm", "a b", "", "$(x)"):
            with self.assertRaises(ValueError):
                node_project.run_command("npm", bad)
        with self.assertRaises(ValueError):
            node_project.run_command("sh", "dev")

    def test_url_local_na_saida(self):
        nxt = "   \x1b[1m▲ Next.js 16.0.1\x1b[22m\n   - Local:        http://localhost:3100\n   - Network:      http://192.168.0.4:3100\n"
        vite = "  VITE v7.1.0  ready in 312 ms\n\n  ➜  Local:   http://127.0.0.1:5173/\n"
        self.assertEqual(node_project.local_url(nxt), "http://localhost:3100")
        self.assertEqual(node_project.local_url(vite), "http://127.0.0.1:5173/")
        self.assertIsNone(node_project.local_url("compilando..."))
