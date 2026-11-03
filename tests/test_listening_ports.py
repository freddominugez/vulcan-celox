"""Portas por aba: só os processos do PTY e descendentes. A saída do lsof foi gravada de um `lsof -F pcn` de verdade."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.server_helpers import ServerTestCase
from vulcan_terminal.core import listening_ports
from vulcan_terminal.core.listening_ports import PortWatcher, descendants, parse_lsof
from vulcan_terminal.core.runner import FakeRunner, Result

LSOF_REAL = "p705\ncrapportd\nf11\nn*:49157\nf12\nn*:49157\np808\ncControlCe\nf9\nn127.0.0.1:7000\nf10\nn[::1]:7001\n"
PS = "  1     0\n 100     1\n 200   100\n 201   200\n 300     1\n 705   200\n 808   300\n"


def lsof_argv(pids):
    return ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-p", pids, "-F", "pcn"]


class ParseTest(unittest.TestCase):
    def test_formato_real(self):
        self.assertEqual(parse_lsof(LSOF_REAL), [(705, 49157, "rapportd"), (705, 49157, "rapportd"), (808, 7000, "ControlCe"), (808, 7001, "ControlCe")])

    def test_descendentes(self):
        children = {1: [100, 300], 100: [200], 200: [201, 705], 300: [808]}
        self.assertEqual(descendants(children, 100), {100, 200, 201, 705})


class WatcherTest(unittest.TestCase):
    def watcher(self, lsof=LSOF_REAL, clock=None, ps=Result(0, PS)):
        self.runner = FakeRunner()
        self.runner.respond(["ps", "-A", "-o", "pid=,ppid="], ps)
        self.runner.respond(lsof_argv("100,200,201,705"), Result(0, lsof))
        return PortWatcher(self.runner, clock=clock or (lambda: 0.0), platform="darwin")

    def test_so_portas_da_aba(self):
        data = self.watcher().ports([("aba1", 100)])
        self.assertEqual(data["ports"], {"aba1": [{"port": 49157, "pid": 705, "command": "rapportd"}]})

    def test_porta_de_outro_processo_nao_aparece_mesmo_se_o_lsof_devolver(self):
        self.assertNotIn(7000, [p["port"] for p in self.watcher().ports([("aba1", 100)])["ports"]["aba1"]])

    def test_sem_shell(self):
        watcher = self.watcher()
        watcher.ports([("aba1", 100)])
        self.assertTrue(all(isinstance(c.argv, tuple) and c.argv[0] in ("ps", "lsof") for c in self.runner.calls))

    def test_cache_de_10_segundos(self):
        now = [0.0]
        watcher = self.watcher(clock=lambda: now[0])
        watcher.ports([("aba1", 100)])
        count = len(self.runner.calls)
        now[0] = 9.0
        watcher.ports([("aba1", 100)])
        self.assertEqual(len(self.runner.calls), count)
        now[0] = 11.0
        watcher.ports([("aba1", 100)])
        self.assertGreater(len(self.runner.calls), count)

    def test_aba_nova_nao_espera_o_cache(self):
        watcher = self.watcher()
        watcher.ports([("aba1", 100)])
        count = len(self.runner.calls)
        watcher.ports([("aba1", 100), ("aba2", 300)])
        self.assertGreater(len(self.runner.calls), count)

    def test_sem_abas_nao_roda_nada(self):
        watcher = self.watcher()
        self.assertEqual(watcher.ports([]), {"ports": {}, "reason": ""})
        self.assertEqual(self.runner.calls, [])

    def test_lsof_sem_nada_e_vazio_sem_erro(self):
        self.runner = FakeRunner()
        self.runner.respond(["ps", "-A", "-o", "pid=,ppid="], Result(0, PS))
        self.runner.respond(lsof_argv("100,200,201,705"), Result(1, ""))
        data = PortWatcher(self.runner, platform="darwin").ports([("aba1", 100)])
        self.assertEqual(data, {"ports": {}, "reason": ""})

    def test_falhas_viram_motivo(self):
        data = self.watcher(ps=Result(127, "")).ports([("aba1", 100)])
        self.assertEqual((data["ports"], data["reason"]), ({}, "ps não rodou"))
        self.runner = FakeRunner()
        self.runner.respond(["ps", "-A", "-o", "pid=,ppid="], Result(0, PS))
        self.runner.respond(lsof_argv("100,200,201,705"), Result(127, ""))
        data = PortWatcher(self.runner, platform="darwin").ports([("aba1", 100)])
        self.assertEqual((data["ports"], data["reason"]), ({}, "lsof não rodou"))


class LinuxTest(unittest.TestCase):
    def test_proc_net_cruza_com_descritores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "net").mkdir()
            head = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
            (root / "net" / "tcp").write_text(head + "   0: 0100007F:1435 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 555 1\n"
                                              "   1: 0100007F:1436 00000000:0000 01 00000000:00000000 00:00000000 00000000  1000        0 556 1\n"
                                              "   2: 0100007F:1437 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 557 1\n")
            (root / "net" / "tcp6").write_text(head)
            for pid, inode, name in ((200, "555", "node"), (900, "557", "outro")):
                (root / str(pid) / "fd").mkdir(parents=True)
                (root / str(pid) / "fd" / "3").symlink_to(f"socket:[{inode}]")
                (root / str(pid) / "comm").write_text(name + "\n")
            (root / "200" / "fd" / "4").symlink_to("socket:[556]")
            runner = FakeRunner()
            runner.respond(["ps", "-A", "-o", "pid=,ppid="], Result(0, " 100 1\n 200 100\n 900 1\n"))
            data = PortWatcher(runner, platform="linux", proc_root=root).ports([("aba1", 100)])
            self.assertEqual(data["ports"], {"aba1": [{"port": 5173, "pid": 200, "command": "node"}]})
            self.assertFalse(any(c.argv[0] == "lsof" for c in runner.calls))


class RotaTest(ServerTestCase):
    def test_rota_exige_token_e_nao_quebra_sem_abas(self):
        self.assertEqual(self.request("GET", "/api/terminals/ports", token=False)[0], 401)
        status, data, _ = self.request("GET", "/api/terminals/ports")
        self.assertEqual((status, data["ports"]), (200, {}))
