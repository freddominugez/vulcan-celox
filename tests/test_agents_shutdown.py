"""Desligamento na ordem certa e observador que para entre arquivos."""

from unittest import mock

from tests import test_agents_api
from tests.helpers import TempDirTestCase
from vulcan_terminal.core.agents.index import AgentIndex
from vulcan_terminal.core.agents.watcher import AgentWatcher


class ShutdownOrderTest(test_agents_api.AgentsServerCase):
    def test_servidor_para_antes_do_banco_fechar(self):
        order = []
        server_shutdown, agents_stop = self.app.server.shutdown, self.app.agents.stop
        with mock.patch.object(self.app.server, "shutdown", lambda: (order.append("http"), server_shutdown())), \
                mock.patch.object(self.app.agents, "stop", lambda: (order.append("agentes"), agents_stop())):
            self.app.shutdown()
        self.assertEqual(order, ["http", "agentes"])
        self.app.shutdown = lambda: None  # o tearDown não desliga de novo


class WatcherStopTest(TempDirTestCase):
    def test_para_entre_arquivos(self):
        for i in range(5):
            path = self.tmp / "claude" / "projects" / "-r" / f"s{i}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"type": "user", "timestamp": "2026-10-31T10:00:00Z", "message": {"content": "oi"}}\n')
        index = AgentIndex(self.tmp / "agentes.db")
        watcher = AgentWatcher(index, {"CLAUDE_CONFIG_DIR": str(self.tmp / "claude"), "CODEX_HOME": str(self.tmp / "x")})
        watcher.scan()
        reads = []
        original = index.update_file

        def slow(agent, path):
            reads.append(path)
            watcher._stop.set()  # o pedido de parada chega durante a primeira leitura
            return original(agent, path)

        with mock.patch.object(index, "update_file", slow):
            watcher.poll(flush=True)
        self.assertEqual(len(reads), 1)
        index.close()
