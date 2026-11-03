"""PTY e WebSocket."""

import os
import re
import socket
import time

from tests.helpers import TempDirTestCase
from tests.server_helpers import ServerTestCase
from tests.test_pty import wait_for
from tests.test_websocket import RawClient
from vulcan_celox.core.pty_session import PtySession, TerminalManager
from vulcan_celox.server.websocket import OP_BINARY, read_frame

ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/tmp", "TERM": "xterm-256color"}


class FdTest(TempDirTestCase):
    def test_close_espera_a_thread_leitora(self):
        s = PtySession(["/bin/sh", "-c", "sleep 30"], str(self.tmp), ENV)
        s.close()
        self.assertFalse(s._reader.is_alive(), "close voltou com a thread leitora ainda usando o fd")

    def test_processo_que_sai_sozinho_fecha_o_fd(self):
        s = PtySession(["/bin/sh", "-c", "exit 3"], str(self.tmp), ENV)
        self.assertTrue(wait_for(lambda: not s.alive))
        self.assertTrue(wait_for(lambda: not s._reader.is_alive()))
        with self.assertRaises(OSError):
            os.fstat(s.fd)
        self.assertEqual(s.exit_code, 3)
        s.close()  # depois de sair sozinho, fechar continua seguro

    def test_abrir_e_fechar_muitas_abas_sem_misturar(self):
        manager = TerminalManager(ENV)
        for n in range(30):
            s = manager.create(str(self.tmp), command=f"echo ABA{n}-FIM")
            self.assertTrue(wait_for(lambda: b"ABA%d-FIM" % n in s.history()), n)
            manager.close(s.id)
            other = re.findall(rb"ABA(\d+)-FIM", s.history())
            self.assertEqual({int(x) for x in other}, {n}, s.history()[-200:])


class OrdemTest(TempDirTestCase):
    def test_historico_do_prime_vem_antes_de_qualquer_bloco_novo(self):
        s = PtySession(["/bin/sh", "-c", "while :; do echo tique; done"], str(self.tmp), ENV)
        try:
            self.assertTrue(wait_for(lambda: len(s.history()) > 1000))
            order = []

            def prime(history):
                order.append(("historico", len(history)))
                time.sleep(0.3)  # a leitora segue recebendo bytes, mas não pode entregar nada antes disto

            s.subscribe(lambda chunk: order.append(("bloco", len(chunk or b""))), prime=prime)
            self.assertTrue(wait_for(lambda: len(order) > 3))
            self.assertEqual(order[0][0], "historico")
            self.assertGreater(order[0][1], 1000)
        finally:
            s.close()


class SaidaTest(TempDirTestCase):
    def test_muitas_abas_que_ignoram_sighup_fecham_juntas(self):
        manager = TerminalManager(ENV)
        for _ in range(8):
            manager.create(str(self.tmp), command="trap '' HUP TERM; sleep 100")
        time.sleep(0.5)
        started = time.monotonic()
        manager.close_all()
        elapsed = time.monotonic() - started
        self.assertEqual(manager.list(), [])
        self.assertLess(elapsed, 4.0, f"close_all levou {elapsed:.1f}s")


class WebSocketTest(ServerTestCase):
    def env(self):
        env = super().env()
        env["SHELL"] = "/bin/sh"
        env["PATH"] = os.environ.get("PATH", "")
        return env

    def tearDown(self):
        self.app.terminals.close_all()
        super().tearDown()

    def open(self, command):
        status, info, _ = self.request("POST", "/api/terminals", body={"command": command})
        self.assertEqual(status, 201)
        return info["id"]

    def test_cliente_que_nao_le_nao_trava_o_terminal(self):
        tid = self.open("head -c 30000000 /dev/zero | tr '\\0' 'x'; echo; echo FIM-$((6*7))")
        parado = RawClient(self.app.server.port, f"/ws/terminals/{tid}?token={self.token}")
        parado.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)  # nunca lê
        pty = self.app.terminals.get(tid)
        self.assertTrue(wait_for(lambda: b"FIM-42" in pty.history(), timeout=30),
                        "o processo ficou preso porque um cliente não lia")
        parado.sock.close()

    def test_reconectar_entrega_o_historico_antes_da_saida_nova(self):
        tid = self.open("i=0; while [ $i -lt 400000 ]; do i=$((i+1)); echo n$i; done")
        time.sleep(0.3)
        for _ in range(15):
            client = RawClient(self.app.server.port, f"/ws/terminals/{tid}?token={self.token}")
            client.sock.settimeout(5)
            data = b""
            while len(data) < 200000:
                fin, opcode, payload = read_frame(client.stream)
                if opcode == OP_BINARY:
                    data += payload
                else:
                    break
            client.sock.close()
            numbers = [int(x) for x in re.findall(rb"\nn(\d+)\r?\n", data)]
            regress = [(a, b) for a, b in zip(numbers, numbers[1:]) if b < a]
            self.assertEqual(regress, [], "saída nova chegou antes do histórico")
