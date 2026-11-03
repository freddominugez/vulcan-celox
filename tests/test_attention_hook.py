"""Hook opcional de atenção: instalação sem duplicar, script que só grava tipo e hora, e prioridade sobre o JSONL."""

import json
import os
import subprocess
import sys
import unittest

from tests.helpers import TempDirTestCase
from vulcan_terminal.core.agents import attention, attention_hook, pairing
from vulcan_terminal.core.agents.model import epoch

T0 = "2026-11-02T10:00:00Z"
NOW = epoch(T0) + 100


class InstalarTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.claude, self.data = self.tmp / "claude", self.tmp / "data"
        self.claude.mkdir()
        self.settings = self.claude / "settings.json"

    def script(self):
        return self.data / "hooks" / attention_hook.SCRIPT_NAME

    def run_hook(self, stdin):
        return subprocess.run([sys.executable, str(self.script())], input=stdin, text=True, capture_output=True, timeout=20)

    def test_instala_duas_vezes_sem_duplicar_e_guarda_o_que_existe(self):
        original = {"model": "opus", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo meu"}]}]}}
        self.settings.write_text(json.dumps(original))
        info = pairing.install_hook(self.claude, self.data, now=1_800_000_000)
        self.assertFalse(info["already_installed"])
        self.assertEqual(json.loads((self.claude / "settings.json.vulcan-backup-1800000000").read_text()), original)
        first = json.loads(self.settings.read_text())
        self.assertEqual(first["hooks"]["Stop"][0], original["hooks"]["Stop"][0])
        self.assertEqual(len(first["hooks"]["Stop"]), 2)
        self.assertEqual(len(first["hooks"]["Notification"]), 1)
        self.assertEqual(len(first["hooks"]["SessionStart"]), 1)
        again = pairing.install_hook(self.claude, self.data, now=1_800_000_100)
        self.assertTrue(again["already_installed"])
        self.assertEqual(json.loads(self.settings.read_text()), first)

    def test_quem_so_tem_o_pareamento_recebe_a_atencao(self):
        pairing.install_hook(self.claude, self.data, now=1)
        settings = json.loads(self.settings.read_text())
        del settings["hooks"]["Notification"], settings["hooks"]["Stop"]
        self.settings.write_text(json.dumps(settings))
        info = pairing.install_hook(self.claude, self.data, now=2)
        self.assertFalse(info["already_installed"])
        self.assertIn("Notification", json.loads(self.settings.read_text())["hooks"])

    def test_script_grava_tipo_e_hora_sem_o_texto(self):
        pairing.install_hook(self.claude, self.data, now=1)
        segredo = "Claude needs your permission to use Bash segredo-do-projeto"
        out = self.run_hook(json.dumps({"session_id": "abc", "hook_event_name": "Notification", "message": segredo}))
        self.assertEqual(out.returncode, 0)
        raw = (attention_hook.attention_dir(self.data) / "abc.json").read_text()
        self.assertNotIn("segredo", raw)
        self.assertEqual(attention_hook.read_records(attention_hook.attention_dir(self.data))["abc"]["kind"], "waiting_permission")

    def test_stop_e_aviso_de_espera_sao_sua_vez(self):
        pairing.install_hook(self.claude, self.data, now=1)
        self.run_hook(json.dumps({"session_id": "a", "hook_event_name": "Stop"}))
        self.run_hook(json.dumps({"session_id": "b", "hook_event_name": "Notification", "message": "waiting for your input"}))
        records = attention_hook.read_records(attention_hook.attention_dir(self.data))
        self.assertEqual((records["a"]["kind"], records["b"]["kind"]), ("your_turn", "your_turn"))

    def test_script_nunca_falha(self):
        pairing.install_hook(self.claude, self.data, now=1)
        for stdin in ("não é json", "[]", '{"session_id": "../fora", "hook_event_name": "Stop"}', '{"session_id": "a", "hook_event_name": "Outro"}'):
            self.assertEqual(self.run_hook(stdin).returncode, 0, stdin)
        self.assertEqual(attention_hook.read_records(attention_hook.attention_dir(self.data)), {})

    def test_leitura_ignora_arquivo_estranho(self):
        folder = attention_hook.attention_dir(self.data)
        folder.mkdir(parents=True)
        (folder / "a.json").write_text("{")
        (folder / "b.json").write_text('{"session_id": "b", "kind": "outro", "at": 1}')
        (folder / "c.json").write_text('{"session_id": "../c", "kind": "your_turn", "at": 1}')
        self.assertEqual(attention_hook.read_records(folder), {})
        self.assertEqual(attention_hook.read_records(self.tmp / "nao-existe"), {})


class PrioridadeTest(unittest.TestCase):
    def test_hook_mais_novo_que_o_arquivo_vence(self):
        raw = {"state": "tool_pending", "since": T0}
        got = attention.resolve(raw, NOW, {"kind": "waiting_permission", "at": epoch(T0) + 5})
        self.assertEqual((got["state"], got["source"]), ("waiting_permission", "hook"))

    def test_linha_mais_nova_no_arquivo_vence_o_hook(self):
        raw = {"state": "running", "since": T0}
        got = attention.resolve(raw, NOW, {"kind": "waiting_permission", "at": epoch(T0) - 5})
        self.assertEqual((got["state"], got["source"]), ("running", "jsonl"))

    def test_pedido_de_permissao_tem_prazo(self):
        hook = {"kind": "waiting_permission", "at": epoch(T0)}
        after = epoch(T0) + attention.PERMISSION_MAX_SECONDS + 1
        self.assertNotEqual((attention.resolve({"state": "tool_pending", "since": T0}, after, hook) or {}).get("state"), "waiting_permission")

    def test_hook_sem_leitura_do_arquivo(self):
        self.assertEqual(attention.resolve(None, NOW, {"kind": "your_turn", "at": NOW - 1})["state"], "your_turn")


if __name__ == "__main__":
    unittest.main()
