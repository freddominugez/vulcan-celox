import os
import time
from pathlib import Path

from tests.helpers import GOLDEN, TempDirTestCase
from tests.server_helpers import ServerTestCase
from vulcan_celox.core.models import Note, Tag, Task
from vulcan_celox.core.session_memory import (MAX_TRANSCRIPT_LINES, extract_transcript, format_duration,
                                                 memory_path, render_session_md, strip_terminal)
from vulcan_celox.core.sessions import SessionRecord

RAW = b"\x1b[32m$\x1b[0m php artisan migrate\r\n  INFO  Running migrations.\r\n\r\n\r\nfeito```\r\n"


def example():
    record = SessionRecord(
        id="abc123def456", title="migrations", site="loja", cwd="/Users/dev/Code/loja", tags=["t-banco"],
        commands=[{"ts": "2026-09-13T20:31:05Z", "cmd": "php artisan migrate"},
                  {"ts": "2026-09-13T20:32:40Z", "cmd": 'git commit -m "add `pedidos`"'}],
        created_at="2026-09-13T20:30:00Z", closed_at="2026-09-13T21:35:30Z", exit_code=0)
    tags = {"t-banco": Tag(id="t-banco", name="banco"), "t-ui": Tag(id="t-ui", name="ui")}
    tasks = [Task(title="Criar tabela pedidos", status="done", priority=1, done_at="2026-09-13T21:00:00Z", tags=["t-banco"]),
             Task(title="Rodar seeders", status="doing", priority=2, due="2026-09-20", assignee="Ana"),
             Task(title="Revisar índices", status="todo", priority=3)]
    notes = [Note(text="Checar | pipes", order=1), Note(text="Senha do banco local\nroot / secret", pinned=True, tags=["t-banco"])]
    return record, tasks, notes, tags


class RenderTest(TempDirTestCase):
    def test_golden(self):
        record, tasks, notes, tags = example()
        transcript, truncated = strip_terminal(RAW)
        text = render_session_md(record, tasks, notes, tags, transcript, truncated)
        self.assertEqual(text, (GOLDEN / "sessao-exemplo.md").read_text(encoding="utf-8"))

    def test_extrai_registro_de_volta(self):
        record, tasks, notes, tags = example()
        transcript, _ = strip_terminal(RAW)
        text = render_session_md(record, tasks, notes, tags, transcript)
        self.assertEqual(extract_transcript(text), (transcript, False))

    def test_strip_terminal(self):
        self.assertEqual(strip_terminal(b"\x1b[1;31merro\x1b[0m\r\n")[0], "erro")
        self.assertEqual(strip_terminal(b"abcdef\rXY\r\n")[0], "XYcdef")
        self.assertEqual(strip_terminal(b"abc\b\bZ\r\n")[0], "aZc")
        self.assertEqual(strip_terminal(b"prompt % ls\x1b[K\r\n")[0], "prompt % ls")
        self.assertEqual(strip_terminal(b"linha velha\rnova\x1b[K\r\n")[0], "nova")
        self.assertEqual(strip_terminal(b"\x1b]0;titulo\x07ok\r\n")[0], "ok")

    def test_limite_de_linhas(self):
        raw = "".join(f"linha {i}\r\n" for i in range(MAX_TRANSCRIPT_LINES + 50)).encode()
        text, truncated = strip_terminal(raw)
        self.assertTrue(truncated)
        self.assertEqual(len(text.splitlines()), MAX_TRANSCRIPT_LINES)
        self.assertTrue(text.endswith(f"linha {MAX_TRANSCRIPT_LINES + 49}"))

    def test_duracao_e_caminho(self):
        self.assertEqual(format_duration("2026-09-13T20:30:00Z", "2026-09-13T20:30:40Z"), "40 s")
        self.assertEqual(format_duration("2026-09-13T20:30:00Z", None), "em andamento")
        record, *_ = example()
        path = memory_path(Path("/dados"), record)
        self.assertEqual(path.as_posix(), "/dados/sessoes/loja/2026-09-13-2030-migrations-abc123def456.md")


def wait_for(fn, timeout=6.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(0.05)
    return fn()


class MemoryIntegrationTest(ServerTestCase):
    def env(self):
        env = super().env()
        env["SHELL"] = "/bin/sh"
        env["PATH"] = os.environ.get("PATH", "")
        return env

    def setUp(self):
        super().setUp()
        (self.tmp / "loja").mkdir()
        self.app.store.save("sites", {"loja": str(self.tmp / "loja")})

    def test_fechar_grava_comando_e_saida(self):
        info = self.request("POST", "/api/terminals", body={"site": "loja", "title": "deploy"})[1]
        pty = self.app.terminals.get(info["id"])
        self.app.hub.on_input(info["id"], b"echo vulcan-memoria\r")
        pty.write(b"echo vulcan-memoria\n")
        wait_for(lambda: b"vulcan-memoria\r\n" in pty.history() and pty.history().count(b"vulcan-memoria") >= 2)
        self.request("DELETE", f"/api/terminals/{info['id']}")
        record = wait_for(lambda: (r := self.app.hub.sessions.get(info["id"])) and r.memory_file and not r.is_open and r)
        text = Path(record.memory_file).read_text(encoding="utf-8")
        self.assertIn("# Sessão: deploy", text)
        self.assertIn("| `echo vulcan-memoria` |", text)
        self.assertIn("vulcan-memoria", extract_transcript(text)[0])
        self.assertIn("encerrada", text)

    def test_exit_no_shell_grava(self):
        info = self.request("POST", "/api/terminals", body={"site": "loja", "command": "echo tchau; exit 0"})[1]
        record = wait_for(lambda: (r := self.app.hub.sessions.get(info["id"])) and not r.is_open and r)
        self.assertTrue(record)
        lido = lambda: Path(record.memory_file).read_text(encoding="utf-8") if record.memory_file else ""
        wait_for(lambda: "tchau" in lido(), timeout=15)  # the session closes before the memory is rewritten
        self.assertIn("tchau", lido())

    def test_editar_tarefa_de_sessao_encerrada_atualiza(self):
        info = self.request("POST", "/api/terminals", body={"site": "loja"})[1]
        task = self.request("POST", "/api/tasks", body={"terminal": info["id"], "title": "tarefa da memória"})[1]
        self.request("DELETE", f"/api/terminals/{info['id']}")
        record = wait_for(lambda: (r := self.app.hub.sessions.get(info["id"])) and not r.is_open and r.memory_file and r)
        path = Path(record.memory_file)
        wait_for(lambda: "tarefa da memória" in path.read_text(encoding="utf-8"))
        self.request("PATCH", f"/api/tasks/{task['id']}", body={"status": "done"})
        self.assertTrue(wait_for(lambda: "- [x] tarefa da memória" in path.read_text(encoding="utf-8")))

    def test_shutdown_grava_sessoes_abertas(self):
        info = self.request("POST", "/api/terminals", body={"site": "loja", "title": "aberta"})[1]
        self.app.hub.finalize_all()
        record = self.app.hub.sessions.get(info["id"])
        self.assertFalse(record.is_open)
        self.assertTrue(Path(record.memory_file).is_file())
