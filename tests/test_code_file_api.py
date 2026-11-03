"""Leitura segura do visor de código: raiz da sessão, links, pasta do agente, tamanho, binário, nome sensível."""

import json
import os
from urllib.parse import quote

from tests.test_agents_api import AgentsServerCase

SID = "44444444-5555-4666-8777-888888888888"


class CodeFileApiTest(AgentsServerCase):
    def setUp(self):
        super().setUp()
        self.project = self.tmp / "projeto"
        self.project.mkdir()
        (self.project / "a.php").write_text("<?php echo '<b>oi</b>';\n", encoding="utf-8")
        self.add_session(self.project, SID)

    def add_session(self, cwd, sid):
        path = self.tmp / "claude" / "projects" / "-tmp-projeto" / f"{sid}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"type": "user", "timestamp": "2026-11-02T10:00:00Z", "cwd": str(cwd),
                                    "message": {"role": "user", "content": "faça"}}) + "\n", encoding="utf-8")
        self.app.agents.refresh()

    def fetch(self, path, sid=SID):
        return self.request("GET", f"/api/code/file?session={sid}&path={quote(str(path))}")

    def assert_refused(self, path, status, reason):
        got, data, _ = self.fetch(path)
        self.assertEqual((got, data.get("reason")), (status, reason), data)
        self.assertNotIn("text", data)

    def test_le_arquivo_relativo_e_absoluto(self):
        for path in ("a.php", self.project / "a.php"):
            status, data, _ = self.fetch(path)
            self.assertEqual(status, 200, data)
            self.assertEqual(data["text"], "<?php echo '<b>oi</b>';\n")
            self.assertEqual(data["language"], "php")
            self.assertEqual(data["size"], len(data["text"]))
            self.assertEqual(len(data["sha256"]), 64)
            self.assertIn("mtime", data)

    def test_subir_de_pasta_recusado(self):
        (self.tmp / "fora.txt").write_text("segredo", encoding="utf-8")
        self.assert_refused("../fora.txt", 403, "outside")
        self.assert_refused(self.tmp / "fora.txt", 403, "outside")

    def test_link_para_fora_recusado(self):
        (self.tmp / "fora.txt").write_text("segredo", encoding="utf-8")
        os.symlink(self.tmp / "fora.txt", self.project / "link.txt")
        os.symlink(self.tmp, self.project / "pasta")
        self.assert_refused("link.txt", 403, "outside")
        self.assert_refused("pasta/fora.txt", 403, "outside")

    def test_pasta_do_agente_recusada_mesmo_como_raiz(self):
        os.symlink(self.tmp / "claude" / "projects", self.project / "dados")
        self.assert_refused("dados", 403, "outside")
        self.add_session(self.tmp / "claude", "55555555-5555-4666-8777-888888888888")
        status, data, _ = self.fetch("settings.json", "55555555-5555-4666-8777-888888888888")
        self.assertEqual((status, data.get("reason")), (403, "root_refused"))

    def test_pasta_que_contem_a_do_agente_recusada(self):
        self.add_session(self.tmp, "66666666-5555-4666-8777-888888888888")
        status, data, _ = self.fetch("projeto/a.php", "66666666-5555-4666-8777-888888888888")
        self.assertEqual((status, data.get("reason")), (403, "root_refused"))

    def test_arquivo_grande_recusado(self):
        (self.project / "g.txt").write_bytes(b"x" * (1024 * 1024 + 1))
        (self.project / "limite.txt").write_bytes(b"x" * (1024 * 1024))
        self.assert_refused("g.txt", 413, "too_large")
        self.assertEqual(self.fetch("limite.txt")[0], 200)

    def test_binario_recusado_e_latin1_aparece(self):
        (self.project / "b.png").write_bytes(b"\x89PNG\r\n\x00\x00")
        (self.project / "tarde.txt").write_bytes(b"x" * 9000 + b"\x00")
        (self.project / "l.txt").write_bytes("acentuação".encode("latin-1"))
        self.assert_refused("b.png", 415, "binary")
        self.assert_refused("tarde.txt", 415, "binary")
        status, data, _ = self.fetch("l.txt")
        self.assertEqual((status, data["lossy"]), (200, True))

    def test_nomes_sensiveis(self):
        for name in (".env", ".env.local", "chave.pem", "x.KEY", "id_rsa", "id_rsa.pub", "credentials", "credentials.json"):
            (self.project / name).write_text("segredo", encoding="utf-8")
            with self.subTest(nome=name):
                self.assert_refused(name, 403, "sensitive")

    def test_sensivel_por_link_e_por_pasta(self):
        (self.project / ".env").write_text("segredo", encoding="utf-8")
        os.symlink(self.project / ".env", self.project / "notas.txt")
        self.assert_refused("notas.txt", 403, "sensitive")
        (self.project / "claro.txt").write_text("nada", encoding="utf-8")
        os.symlink(self.project / "claro.txt", self.project / ".env.link")
        self.assert_refused(".env.link", 403, "sensitive")
        (self.project / ".git").mkdir()
        (self.project / ".git" / "config").write_text("url = https://token@x", encoding="utf-8")
        self.assert_refused(".git/config", 403, "sensitive")

    def test_apagado_e_pasta(self):
        self.assert_refused("sumiu.txt", 404, "missing")
        (self.project / "sub").mkdir()
        self.assert_refused("sub", 403, "unreadable")

    def test_fifo_nao_trava(self):
        os.mkfifo(self.project / "fila")
        self.assert_refused("fila", 403, "unreadable")

    def test_caminho_invalido_e_sessao_desconhecida(self):
        self.assert_refused("", 400, "invalid")
        self.assertEqual(self.request("GET", "/api/code/file?session=-x&path=a.php")[0], 404)
        self.assertEqual(self.fetch("a.php", "99999999-5555-4666-8777-888888888888")[0], 404)
        self.assert_refused("a\x00.php", 400, "invalid")

    def test_exige_token(self):
        path = f"/api/code/file?session={SID}&path=a.php"
        self.assertEqual(self.request("GET", path, token=False)[0], 401)

    def test_nao_existe_escrita(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(metodo=method):
                status = self.request(method, f"/api/code/file?session={SID}&path=a.php", {"text": "x"})[0]
                self.assertIn(status, (404, 405))
        self.assertEqual((self.project / "a.php").read_text(encoding="utf-8"), "<?php echo '<b>oi</b>';\n")

    def test_abrir_no_editor_tem_a_mesma_checagem(self):
        (self.project / ".env").write_text("segredo", encoding="utf-8")
        body = {"kind": "session_file", "session": SID}
        self.assertEqual(self.request("POST", "/api/open", {**body, "target": "a.php"})[0], 200)
        self.assertEqual(self.request("POST", "/api/open", {**body, "target": "../fora.txt"})[0], 403)
        self.assertEqual(self.request("POST", "/api/open", {**body, "target": ".env"})[0], 403)
        self.assertEqual(self.request("POST", "/api/open", {**body, "target": "sumiu.txt"})[0], 404)
        self.assertEqual(self.request("POST", "/api/open", {**body, "session": "x", "target": "a.php"})[0], 404)
