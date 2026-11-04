from tests.test_pty import wait_for
import os

from tests.server_helpers import ServerTestCase


class FsApiTest(ServerTestCase):
    def env(self):
        env = super().env()
        env["SHELL"] = "/bin/sh"
        env["PATH"] = os.environ.get("PATH", "")
        return env

    def test_validacao_da_pasta(self):
        (self.tmp / "Code" / "loja").mkdir(parents=True)
        (self.tmp / "arquivo.txt").write_text("x", encoding="utf-8")
        ok = self.request("GET", "/api/fs/folder?path=~/Code/loja")[1]
        self.assertEqual((ok["exists"], ok["is_dir"], ok["short"], ok["name"]), (True, True, os.path.join("~", "Code", "loja"), "loja"))
        self.assertEqual(ok["path"], str(self.tmp / "Code" / "loja"))
        missing = self.request("GET", "/api/fs/folder?path=~/nao-existe")[1]
        self.assertFalse(missing["exists"])
        file = self.request("GET", f"/api/fs/folder?path={self.tmp / 'arquivo.txt'}")[1]
        self.assertEqual((file["exists"], file["is_dir"]), (True, False))
        self.assertEqual(self.request("GET", "/api/fs/folder?path=")[0], 400)
        self.assertEqual(self.request("GET", "/api/fs/folder?path=/", token=False)[0], 401)

    def test_recentes_sem_duplicata_e_terminal_na_pasta(self):
        loja = self.tmp / "loja"
        blog = self.tmp / "blog"
        loja.mkdir()
        blog.mkdir()
        self.app.store.save("sites", {"loja": str(loja), "blog": str(blog)})
        a = self.request("POST", "/api/terminals", body={"site": "loja", "cwd": "~/blog"})[1]
        self.assertEqual(a["cwd"], str(blog))
        self.request("POST", "/api/terminals", body={"site": "loja"})
        gone = self.tmp / "sumiu"
        gone.mkdir()
        aberta = self.request("POST", "/api/terminals", body={"cwd": str(gone)})[1]
        self.request("DELETE", f"/api/terminals/{aberta['id']}")  # on Windows, the shell holds the folder while it lives

        def remover():
            try:
                gone.rmdir()
                return True
            except OSError:
                return False
        self.assertTrue(wait_for(remover))
        data = self.request("GET", "/api/fs/recent")[1]
        paths = [r["path"] for r in data["recent"]]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertIn(str(blog), paths)
        self.assertIn(str(loja), paths)
        self.assertNotIn(str(gone), paths)
        self.assertEqual(data["home"]["short"], "~")
        self.assertEqual(self.request("POST", "/api/terminals", body={"cwd": "~/nada"})[0], 400)
