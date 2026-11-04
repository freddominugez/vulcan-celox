"""Windows: one part checks the choices on any system; the other only runs on Windows, with a real ConPTY."""

import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

from vulcan_celox.core import keychain, listening_ports, oscompat, trash
from vulcan_celox.core.pty_session import TerminalManager
from vulcan_celox.core.runner import Runner

WINDOWS = sys.platform == "win32"


class EscolhasTest(unittest.TestCase):
    def test_pasta_de_dados(self):
        path = oscompat.default_data_dir({"APPDATA": "/AppData", "HOME": "/h"}, system="win32")
        self.assertEqual(path.name, "VulcanCelox")
        self.assertEqual(path.parent, Path("/AppData"))

    def test_abrir_nunca_passa_por_cmd(self):
        none = lambda _name: None
        for kind, target in (("url", "https://x.test/a&b"), ("folder", "C:\\a&b"), ("file", "C:\\a&b.md"), ("editor", "C:\\a&calc.txt")):
            argv = oscompat.open_argv(kind, target, {}, system="win32", which=none)
            self.assertNotIn(Path(argv[0]).name.lower(), ("cmd", "cmd.exe"), argv)
            self.assertEqual(argv[-1], target)

    def test_editor_cmd_nao_e_chamado(self):
        argv = oscompat.open_argv("editor", "C:\\a.txt", {}, system="win32", which=lambda _n: "C:\\VS\\bin\\code.cmd")
        self.assertFalse(argv[0].lower().endswith(".cmd"), argv)

    def test_shell(self):
        self.assertEqual(oscompat.interactive_argv("C:\\w\\powershell.exe", None), ["C:\\w\\powershell.exe", "-NoLogo"])
        self.assertEqual(oscompat.interactive_argv("cmd.exe", "dir"), ["cmd.exe", "/k", "dir"])
        self.assertEqual(oscompat.shell_command_argv("/bin/zsh", "ls"), ["/bin/zsh", "-lc", "ls"])
        self.assertEqual(oscompat.interactive_argv("/bin/zsh", None), ["/bin/zsh", "-l"])

    def test_netstat(self):
        text = ("  Proto  Local Address          Foreign Address        State           PID\n"
                "  TCP    0.0.0.0:5173           0.0.0.0:0              LISTENING       200\n"
                "  TCP    [::]:8080              [::]:0                 LISTENING       300\n"
                "  TCP    127.0.0.1:5000         127.0.0.1:6000         ESTABLISHED     200\n"
                "  TCP    0.0.0.0:9999           0.0.0.0:0              LISTENING       999\n")
        self.assertEqual(listening_ports.parse_netstat(text, [200, 300]), [(200, 5173, ""), (300, 8080, "")])


@unittest.skipUnless(WINDOWS, "só no Windows")
class ConPtyTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.manager = TerminalManager(dict(os.environ))
        self.addCleanup(self.manager.close_all)

    def wait_for(self, session, text, seconds=60):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if text in session.history().decode("utf-8", "replace"):
                return True
            time.sleep(0.2)
        self.fail(f"não apareceu {text!r}; saída: {session.history().decode('utf-8', 'replace')[-800:]}")

    def test_cmd_responde(self):
        self.manager.shell = lambda: os.environ.get("COMSPEC", "cmd.exe")
        session = self.manager.create(self.dir)
        session.write(b"echo marca-cmd-%USERNAME%x\r")
        started = time.time()
        self.wait_for(session, "marca-cmd-")
        print("cmd respondeu em", round(time.time() - started, 1))

    def test_powershell_do_windows_responde(self):
        self.manager.shell = lambda: "powershell.exe"
        session = self.manager.create(self.dir)
        session.write(b"echo ('mar' + 'ca-ps')\r")
        started = time.time()
        self.wait_for(session, "marca-ps")
        print("powershell respondeu em", round(time.time() - started, 1))

    def test_comando_responde_com_acento(self):
        session = self.manager.create(self.dir)
        session.write("echo ('acen' + 'tuação')\r".encode("utf-8"))
        self.wait_for(session, "acentuação")

    def test_redimensiona(self):
        session = self.manager.create(self.dir, cols=80, rows=24)
        session.resize(40, 120)
        session.write(b"$Host.UI.RawUI.WindowSize.Width\r")
        self.wait_for(session, "120")

    def test_comando_inicial_e_saida(self):
        session = self.manager.create(self.dir, command="exit 7")
        deadline = time.time() + 60
        while session.alive and time.time() < deadline:
            time.sleep(0.2)
        self.assertEqual(session.exit_code, 7)

    def test_fechar_nao_deixa_processo(self):
        session = self.manager.create(self.dir)
        win = session._win
        pid = session.pid
        self.manager.close(session.id)
        self.assertFalse(session.alive)
        from vulcan_celox.core.win32 import process_table
        self.assertNotIn(pid, [row[0] for row in process_table()])
        self.assertTrue(win.closed)

    def test_porta_da_aba(self):
        session = self.manager.create(self.dir)
        code = "import http.server as h;s=h.HTTPServer(('127.0.0.1',0),h.BaseHTTPRequestHandler);s.serve_forever()"
        session.write(f'& "{sys.executable}" -c "{code}"\r'.encode("utf-8"))
        watcher = listening_ports.PortWatcher(Runner(), clock=time.time, platform="win32")
        deadline = time.time() + 60
        ports = {}
        while time.time() < deadline and not ports:
            watcher.cached = None
            ports = watcher.ports([(session.id, session.pid)])["ports"]
            time.sleep(0.5)
        self.assertTrue(ports.get(session.id), "a porta do processo filho não apareceu")


@unittest.skipUnless(WINDOWS, "só no Windows")
class SistemaTest(unittest.TestCase):
    def test_lixeira(self):
        folder = Path(tempfile.mkdtemp())
        target = folder / "apagar & depois.txt"
        target.write_text("x", encoding="utf-8")
        where = trash.move_to_trash(target, folder / "dados", Runner(), system="win32")
        self.assertFalse(target.exists())
        self.assertEqual(where, target, "foi para a Lixeira do Windows, não para a reserva")

    def test_credencial(self):
        store = keychain.WindowsCredentialStore(service="vulcan-celox-teste")
        self.addCleanup(store.delete)
        key = "sk-ant-" + "b" * 40
        store.set(key)
        self.assertEqual(store.get(), key)
        store.delete()
        self.assertIsNone(store.get())

    def test_processo_sem_janela_roda(self):
        result = Runner().run_shell("Write-Output ola", timeout=30)
        self.assertEqual(result.stdout.strip(), "ola")

    def test_pasta_de_codigo(self):
        from vulcan_celox.core import code_files
        folder = tempfile.mkdtemp()
        Path(folder, "a.py").write_text("print('ç')\n", encoding="utf-8")
        got = code_files.read_for_viewer("a.py", [folder])
        self.assertEqual(got["text"].replace("\r\n", "\n"), "print('ç')\n")
        with self.assertRaises(code_files.CodeReadError):
            code_files.read_for_viewer("..\\fora.txt", [folder])
