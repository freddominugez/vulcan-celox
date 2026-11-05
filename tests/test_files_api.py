"""Code screen routes: which folders open, what the tree lists, what it refuses."""

import json
import os
import shutil
import subprocess
import unittest
import unittest.mock
from urllib.parse import quote

from tests.server_helpers import ServerTestCase

GIT = shutil.which("git")


class FilesCase(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.project = self.tmp / "projeto"
        self.project.mkdir()
        self.root = str(self.project.resolve())
        self.assertEqual(self.request("POST", "/api/files/roots", body={"path": self.root})[0], 200)

    def get(self, route, **args):
        query = "&".join(f"{k}={quote(str(v))}" for k, v in {"root": self.root, **args}.items())
        return self.request("GET", f"/api/files/{route}?{query}")


class RaizesTest(ServerTestCase):
    def test_escolher_listar_e_remover(self):
        pasta = self.tmp / "app-a"
        pasta.mkdir()
        status, data = self.request("POST", "/api/files/roots", body={"path": str(pasta)})[:2]
        self.assertEqual(status, 200)
        real = str(pasta.resolve())
        self.assertEqual(data["added"], real)
        item = next(r for r in data["roots"] if r["path"] == real)
        self.assertEqual((item["source"], item["removable"], item["exists"]), ("chosen", True, True))
        self.assertEqual(json.loads((self.tmp / "home" / "code_roots.json").read_text(encoding="utf-8"))["data"], [real])
        self.assertEqual(self.request("GET", f"/api/files/tree?root={quote(real)}")[0], 200)
        status, data = self.request("DELETE", f"/api/files/roots?path={quote(real)}")[:2]
        self.assertEqual(status, 200)
        self.assertNotIn(real, [r["path"] for r in data["roots"]])
        self.assertTrue(pasta.is_dir(), "remover só tira da lista")
        self.assertEqual(self.request("GET", f"/api/files/tree?root={quote(real)}")[0], 403)

    def test_recusas_com_motivo(self):
        for path, why in ((str(self.tmp), "home"), (os.path.abspath(os.sep), "disk"), (str(self.tmp / "home"), "app_data")):
            status, data = self.request("POST", "/api/files/roots", body={"path": path})[:2]
            self.assertEqual((status, data["reason"], data["why"]), (403, "root_refused", why), path)
        status, data = self.request("POST", "/api/files/roots", body={"path": str(self.tmp / "nada")})[:2]
        self.assertEqual((status, data["reason"]), (400, "missing"))
        self.assertEqual(self.request("POST", "/api/files/roots", body={"path": 3})[0], 400)
        self.assertEqual(self.request("DELETE", "/api/files/roots")[0], 400)

    def test_recusa_dados_de_agente(self):
        dados = self.tmp / ".claude"
        (dados / "projects").mkdir(parents=True)
        for path in (dados, dados / "projects"):
            status, data = self.request("POST", "/api/files/roots", body={"path": str(path)})[:2]
            self.assertEqual((status, data.get("why")), (403, "agent_data"), path)

    def test_limite_de_50(self):
        for i in range(50):
            (self.tmp / f"p{i}").mkdir()
            self.assertEqual(self.request("POST", "/api/files/roots", body={"path": str(self.tmp / f"p{i}")})[0], 200)
        (self.tmp / "p50").mkdir()
        status, data = self.request("POST", "/api/files/roots", body={"path": str(self.tmp / "p50")})[:2]
        self.assertEqual((status, data["reason"]), (400, "limit"))
        # the same folder again takes no new slot
        self.assertEqual(self.request("POST", "/api/files/roots", body={"path": str(self.tmp / "p3")})[0], 200)

    def test_pasta_conhecida_vale_sem_escolher(self):
        site = self.tmp / "loja"
        site.mkdir()
        self.app.store.save("sites", {"loja": str(site)})
        self.app.files.roots.known_at = -1000
        data = self.request("GET", "/api/files/roots")[1]
        item = next(r for r in data["roots"] if r["path"] == str(site.resolve()))
        self.assertEqual((item["source"], item["removable"]), ("site", False))
        self.assertEqual(self.request("GET", f"/api/files/tree?root={quote(str(site.resolve()))}")[0], 200)

    def test_duas_escolhas_ao_mesmo_tempo_nao_perdem_pasta(self):
        import threading
        pastas = [self.tmp / f"c{i}" for i in range(4)]
        for pasta in pastas:
            pasta.mkdir()
        threads = [threading.Thread(target=self.request, args=("POST", "/api/files/roots"), kwargs={"body": {"path": str(p)}}) for p in pastas]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        self.assertEqual(sorted(self.app.files.roots.chosen()), sorted(str(p.resolve()) for p in pastas))

    def test_sem_rota_de_escrita(self):
        write = [r for r in self.app.server.routes if r[0] in ("POST", "PUT", "PATCH", "DELETE") and "/api/files/" in r[1].pattern]
        self.assertEqual(sorted(r[1].pattern for r in write), ["^/api/files/roots$", "^/api/files/roots$"])


class AbrirNoEditorTest(FilesCase):
    def open(self, **body):
        return self.request("POST", "/api/open", body={"kind": "code_file", **body})[:2]

    def test_abre_arquivo_da_pasta(self):
        (self.project / "sub").mkdir()
        (self.project / "sub" / "a.py").write_text("x", encoding="utf-8")
        self.assertEqual(self.open(root=self.root, target="sub/a.py")[0], 200)
        self.assertIn(str(self.project.resolve() / "sub" / "a.py"), self.fake.calls[-1].argv)

    def test_recusas(self):
        (self.project / ".env").write_text("x", encoding="utf-8")
        fora = self.tmp / "fora.txt"
        fora.write_text("x", encoding="utf-8")
        os.symlink(fora, self.project / "link.txt")
        outra = self.tmp / "outra"
        outra.mkdir()
        before = len(self.fake.calls)
        self.assertEqual(self.open(root=self.root, target=".env")[0], 403)
        self.assertEqual(self.open(root=self.root, target="link.txt")[0], 403)
        self.assertEqual(self.open(root=self.root, target="../fora.txt")[0], 400)
        self.assertEqual(self.open(root=self.root, target="nada.txt")[0], 404)
        self.assertEqual(self.open(root=str(outra), target="a")[0], 403)
        self.assertEqual(self.open(root=3, target="a")[0], 403)
        self.assertEqual(len(self.fake.calls), before, "nenhum programa pode ter rodado")


class ArvoreTest(FilesCase):
    def test_ordem_e_campos(self):
        (self.project / "b.txt").write_text("oi", encoding="utf-8")
        (self.project / "Zeta").mkdir()
        (self.project / "alfa").mkdir()
        (self.project / "A.txt").write_text("x", encoding="utf-8")
        (self.project / ".env").write_text("SEGREDO=1", encoding="utf-8")
        (self.project / ".git").mkdir()
        data = self.get("tree")[1]
        self.assertEqual([e["name"] for e in data["entries"]], ["alfa", "Zeta", ".env", "A.txt", "b.txt"])
        b = data["entries"][-1]
        self.assertEqual((b["rel"], b["kind"], b["size"], b["sensitive"], b["ignored"]), ("b.txt", "file", 2, False, False))
        self.assertTrue(data["entries"][2]["sensitive"])
        self.assertFalse(data["truncated"])

    def test_subpasta_e_link_nao_seguido(self):
        fora = self.tmp / "fora"
        fora.mkdir()
        (fora / "segredo.txt").write_text("nao", encoding="utf-8")
        (self.project / "sub").mkdir()
        (self.project / "sub" / "a.py").write_text("x = 1\n", encoding="utf-8")
        os.symlink(fora, self.project / "saida")
        os.symlink(fora / "segredo.txt", self.project / "saida.txt")
        os.symlink(self.project / "sub", self.project / "atalho")
        data = self.get("tree")[1]
        kinds = {e["name"]: e["kind"] for e in data["entries"]}
        self.assertEqual((kinds["saida"], kinds["saida.txt"], kinds["atalho"], kinds["sub"]), ("link", "link", "link", "dir"))
        self.assertEqual([e["rel"] for e in self.get("tree", path="sub")[1]["entries"]], ["sub/a.py"])
        for path in ("saida", "atalho", "atalho/../sub"):
            self.assertIn(self.get("tree", path=path)[0], (400, 403), path)
        status, body = self.get("read", path="saida.txt")[:2]
        self.assertEqual((status, body["reason"]), (403, "outside"))

    def test_caminhos_recusados(self):
        (self.project / "a.txt").write_text("x", encoding="utf-8")
        for route in ("tree", "read", "diff"):
            for path in ("../fora", "a/../../fora", os.path.abspath(os.sep), str(self.project / "a.txt"), "a\x00b"):
                status, body = self.get(route, path=path)[:2]
                self.assertEqual((status, body["reason"]), (400, "invalid"), (route, path))

    def test_raiz_nao_permitida(self):
        outra = self.tmp / "outra"
        outra.mkdir()
        for route in ("tree", "read", "diff"):
            status, body = self.request("GET", f"/api/files/{route}?root={quote(str(outra))}&path=a")[:2]
            self.assertEqual((status, body["reason"]), (403, "root_refused"))
            self.assertEqual(self.request("GET", f"/api/files/{route}?path=a")[0], 403)
        self.assertEqual(self.request("GET", f"/api/files/tree?root={quote(self.root)}", token=False)[0], 401)

    def test_pasta_git_nunca_abre(self):
        (self.project / ".git").mkdir()
        (self.project / ".git" / "config").write_text("x", encoding="utf-8")
        (self.project / ".aws").mkdir()
        (self.project / ".aws" / "credentials").write_text("x", encoding="utf-8")
        for path in (".git", ".GIT", ".aws", ".git/config"):
            self.assertEqual(self.get("tree", path=path)[0], 403, path)
        self.assertEqual(self.get("read", path=".git/config")[1]["reason"], "sensitive")
        self.assertEqual(self.get("read", path=".aws/credentials")[1]["reason"], "sensitive")
        self.assertTrue(next(e for e in self.get("tree")[1]["entries"] if e["name"] == ".aws")["sensitive"])

    def test_5001_entradas(self):
        for i in range(5001):
            (self.project / f"f{i:05}").touch()
        data = self.get("tree")[1]
        self.assertTrue(data["truncated"])
        self.assertEqual((len(data["entries"]), data["total"], data["entries"][0]["name"]), (5000, 5001, "f00000"))

    def test_nome_com_caracteres_especiais(self):
        nomes = ["<img src=x onerror=alert(1)>.php", "com espaço & #hash?.txt", "çãõ-日本語.md", "aspas\"'.js"]
        for nome in nomes:
            (self.project / nome).write_text(nome, encoding="utf-8")
        data = self.get("tree")[1]
        self.assertEqual(sorted(e["name"] for e in data["entries"]), sorted(nomes))
        for nome in nomes:
            status, body = self.get("read", path=nome)[:2]
            self.assertEqual((status, body["text"]), (200, nome))

    @unittest.skipIf(os.name == "nt" or os.uname().sysname == "Darwin", "o sistema de arquivos aceita qualquer byte só no Linux")
    def test_nome_que_nao_e_utf8(self):
        with open(os.path.join(os.fsencode(self.root), b"nome-\xff.txt"), "wb") as fh:
            fh.write(b"x")
        data = self.get("tree")[1]
        self.assertTrue(data["entries"][0]["bad_name"])

    def test_leitura_limites(self):
        (self.project / "bin").write_bytes(b"a\x00b")
        (self.project / "grande.txt").write_bytes(b"a" * (1024 * 1024 + 1))
        (self.project / ".env").write_text("x", encoding="utf-8")
        (self.project / "ok.py").write_text("x = 1\n", encoding="utf-8")
        self.assertEqual(self.get("read", path="bin")[1]["reason"], "binary")
        self.assertEqual(self.get("read", path="grande.txt")[1]["reason"], "too_large")
        self.assertEqual(self.get("read", path=".env")[1]["reason"], "sensitive")
        self.assertEqual(self.get("read", path="nada.txt")[1]["reason"], "missing")
        self.assertEqual(self.get("read", path="ok.py")[1]["language"], "python")

    def test_pasta_apagada(self):
        (self.project / "sub").mkdir()
        (self.project / "sub").rmdir()
        status, body = self.get("tree", path="sub")[:2]
        self.assertEqual((status, body["reason"]), (404, "missing"))


class IgnoradosTest(FilesCase):
    def test_lista_fixa_sem_git(self):
        (self.project / "node_modules").mkdir()
        (self.project / "src").mkdir()
        (self.project / "node_modules" / "x").mkdir()
        data = {e["name"]: e["ignored"] for e in self.get("tree")[1]["entries"]}
        self.assertEqual(data, {"node_modules": True, "src": False})
        self.assertTrue(self.get("tree", path="node_modules")[1]["entries"][0]["ignored"])

    @unittest.skipUnless(GIT, "sem git")
    def test_gitignore_vence_a_lista_fixa(self):
        subprocess.run(["git", "init", "-q", self.root], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (self.project / ".gitignore").write_text("gerado/\n*.log\nç-*.txt\n", encoding="utf-8")
        for nome in ("gerado", "dist", "src"):
            (self.project / nome).mkdir()
        (self.project / "gerado" / "a").touch()
        (self.project / "dist" / "a").touch()
        (self.project / "src" / "b.log").touch()
        (self.project / "src" / "c.py").touch()
        (self.project / "ç-a.txt").touch()
        data = {e["name"]: e["ignored"] for e in self.get("tree")[1]["entries"]}
        self.assertEqual((data["gerado"], data["dist"], data["src"], data["ç-a.txt"]), (True, False, False, True))
        data = {e["name"]: e["ignored"] for e in self.get("tree", path="src")[1]["entries"]}
        self.assertEqual(data, {"b.log": True, "c.py": False})

    def test_tempo_limite_cai_na_lista_fixa(self):
        from vulcan_celox.core import file_tree
        with unittest.mock.patch("vulcan_celox.core.file_tree.capture", return_value=(None, b"", True)):
            self.assertTrue(file_tree.git_ignored(self.root).fixed)


@unittest.skipUnless(GIT, "sem git")
class BuscaTest(FilesCase):
    def repo(self):
        for args in (["init", "-q"], ["config", "user.email", "a@b.c"], ["config", "user.name", "x"]):
            subprocess.run(["git", "-C", self.root, *args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def commit(self):
        for args in (["add", "-A"], ["commit", "-qm", "i"]):
            subprocess.run(["git", "-C", self.root, *args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def test_sem_repositorio(self):
        data = self.get("search", q="x")[1]
        self.assertEqual((data["available"], data["reason"]), (False, "no_repo"))

    def test_sem_git(self):
        with unittest.mock.patch("vulcan_celox.core.file_tree.capture", return_value=(None, b"", False)):
            self.assertEqual(self.get("search", q="x")[1]["reason"], "no_git")

    def test_resultados_e_nomes_especiais(self):
        self.repo()
        (self.project / "sub").mkdir()
        (self.project / "sub" / "çã o.py").write_text("um\nacho:isto\n", encoding="utf-8")
        (self.project / ".env").write_text("acho:isto\n", encoding="utf-8")
        (self.project / "b.bin").write_bytes(b"acho:isto\x00")
        self.commit()
        data = self.get("search", q="acho:isto")[1]
        self.assertEqual(data["results"], [{"rel": "sub/çã o.py", "line": 2, "text": "acho:isto"}])
        self.assertFalse(data["truncated"])
        self.assertEqual(self.get("search", q="não existe aqui")[1]["results"], [])

    def test_texto_com_traco_nao_vira_opcao(self):
        self.repo()
        (self.project / "a.txt").write_text("--help e -v\n", encoding="utf-8")
        self.commit()
        for text in ("--help", "-v"):
            self.assertEqual(len(self.get("search", q=text)[1]["results"]), 1, text)

    def test_limites(self):
        self.repo()
        (self.project / "a.txt").write_text("alvo " + "x" * 400 + "\n" + "alvo\n" * 600, encoding="utf-8")
        self.commit()
        data = self.get("search", q="alvo")[1]
        self.assertEqual((len(data["results"]), data["truncated"]), (500, True))
        self.assertEqual(len(data["results"][0]["text"]), 300)
        self.assertEqual(self.get("search")[0], 400)
        self.assertEqual(self.get("search", q="a\x00b")[0], 400)

    def test_foto_para_abertura_rapida(self):
        (self.project / "s").mkdir()
        (self.project / "s" / "a.py").touch()
        (self.project / "b.py").touch()
        (self.project / "node_modules").mkdir()
        (self.project / "node_modules" / "x.js").touch()
        data = self.get("photo")[1]
        self.assertEqual((data["files"], data["partial"]), (["b.py", "s/a.py"], False))


class DiffTest(FilesCase):
    def test_sem_git_no_diff(self):
        (self.project / "a.py").write_text("x\n", encoding="utf-8")
        data = self.get("diff", path="a.py")[1]
        self.assertFalse(data["available"])
        self.assertIn(data["reason"], ("no_repo", "no_git"))

    @unittest.skipUnless(GIT, "sem git")
    def test_diff_contra_head(self):
        for args in (["init", "-q"], ["config", "user.email", "a@b.c"], ["config", "user.name", "x"]):
            subprocess.run(["git", "-C", self.root, *args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (self.project / "a.py").write_text("x\n", encoding="utf-8")
        for args in (["add", "-A"], ["commit", "-qm", "i"]):
            subprocess.run(["git", "-C", self.root, *args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (self.project / "a.py").write_text("y\n", encoding="utf-8")
        data = self.get("diff", path="a.py")[1]
        self.assertEqual((data["old"], data["new"], data["status"]), ("x\n", "y\n", "modified"))
        (self.project / ".env").write_text("s", encoding="utf-8")
        self.assertEqual(self.get("diff", path=".env")[1]["reason"], "sensitive")


if __name__ == "__main__":
    unittest.main()
