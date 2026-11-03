"""Pareamento entre a aba do terminal e a sessão de agente, por hook e por reserva."""

import json
import os
import subprocess
import sys

from tests import test_agents_api
from tests.helpers import TempDirTestCase
from vulcan_terminal.core.agents import pairing
from vulcan_terminal.core.agents.model import AgentSession
from vulcan_terminal.core.sessions import SessionRecord

CLAUDE_SID = "11111111-2222-4333-8444-555555555555"


def agent(sid, cwd, started, kind="claude"):
    return AgentSession(id=sid, agent=kind, file_path="/x", cwd=cwd, project_root=cwd, started_at=started)


def tab(tid, cwd, created, commands=(), theme="oceano"):
    return SessionRecord(id=tid, cwd=cwd, created_at=created, theme=theme,
                         commands=[{"ts": ts, "cmd": cmd} for ts, cmd in commands])


class ResolveTest(TempDirTestCase):
    def test_reserva_pela_criacao_da_aba(self):
        pairs = pairing.resolve([agent("s1", "/r/loja", "2026-10-31T10:00:20Z")],
                                [tab("t1", "/r/loja", "2026-10-31T10:00:00Z")], {})
        self.assertEqual(pairs, {"s1": {"terminal_id": "t1", "theme": "oceano", "how": "pasta e horário"}})

    def test_reserva_pelo_comando_digitado_depois(self):
        t = tab("t1", "/r/loja", "2026-10-31T08:00:00Z", [("2026-10-31T10:00:00Z", "ls"), ("2026-10-31T10:30:00Z", "claude --resume")])
        pairs = pairing.resolve([agent("s1", "/r/loja", "2026-10-31T10:30:04Z")], [t], {})
        self.assertEqual(pairs["s1"]["terminal_id"], "t1")

    def test_sem_par_fora_da_janela_ou_em_outra_pasta(self):
        t = tab("t1", "/r/loja", "2026-10-31T10:00:00Z")
        self.assertEqual(pairing.resolve([agent("s1", "/r/loja", "2026-10-31T10:02:00Z")], [t], {}), {})
        self.assertEqual(pairing.resolve([agent("s1", "/r/outra", "2026-10-31T10:00:10Z")], [t], {}), {})
        self.assertEqual(pairing.resolve([agent("s1", "/r/loja", "2026-10-31T09:59:50Z")], [t], {}), {})  # antes da aba

    def test_comando_do_outro_agente_nao_pareia(self):
        t = tab("t1", "/r/loja", "2026-10-31T08:00:00Z", [("2026-10-31T10:00:00Z", "codex")])
        self.assertEqual(pairing.resolve([agent("s1", "/r/loja", "2026-10-31T10:00:05Z", "claude")], [t], {}), {})
        self.assertIn("s1", pairing.resolve([agent("s1", "/r/loja", "2026-10-31T10:00:05Z", "codex")], [t], {}))

    def test_aba_mais_proxima_vence(self):
        tabs = [tab("t1", "/r/loja", "2026-10-31T10:00:00Z"), tab("t2", "/r/loja", "2026-10-31T10:00:15Z", theme="ardosia")]
        pairs = pairing.resolve([agent("s1", "/r/loja", "2026-10-31T10:00:20Z")], tabs, {})
        self.assertEqual(pairs["s1"]["terminal_id"], "t2")

    def test_arquivo_do_hook_vence_a_reserva(self):
        tabs = [tab("t1", "/r/loja", "2026-10-31T10:00:00Z"), tab("t9", "/r/loja", "2026-10-31T07:00:00Z", theme="homebrew")]
        files = {"s1": {"terminal_id": "t9", "theme": "homebrew"}}
        pairs = pairing.resolve([agent("s1", "/r/loja", "2026-10-31T10:00:20Z")], tabs, files)
        self.assertEqual(pairs["s1"], {"terminal_id": "t9", "theme": "homebrew", "how": "hook"})

    # ── só quem nasce de uma aba, e um lançamento por sessão ────────────────────
    def test_subagente_e_desktop_nao_pareiam_por_pasta_e_horario(self):
        t = tab("t1", "/r/loja", "2026-10-31T08:00:00Z", [("2026-10-31T10:00:00Z", "codex")])
        principal = agent("principal", "/r/loja", "2026-10-31T10:00:05Z", "codex")
        sub = agent("sub", "/r/loja", "2026-10-31T10:00:40Z", "codex")
        sub.origin = "subagent"
        desk = agent("desk", "/r/loja", "2026-10-31T10:00:10Z", "codex")
        desk.origin = "desktop"
        self.assertEqual(set(pairing.resolve([sub, desk, principal], [t], {})), {"principal"})

    def test_duas_abas_e_duas_sessoes_que_demoram_para_nascer(self):
        # as duas sessões nascem depois dos dois lançamentos: a mais antiga fica com o primeiro
        a = tab("a", "/r/loja", "2026-10-31T08:00:00Z", [("2026-10-31T10:00:00Z", "codex")])
        b = tab("b", "/r/loja", "2026-10-31T08:00:00Z", [("2026-10-31T10:00:05Z", "codex")])
        s1 = agent("s1", "/r/loja", "2026-10-31T10:00:06Z", "codex")
        s2 = agent("s2", "/r/loja", "2026-10-31T10:00:08Z", "codex")
        pairs = pairing.resolve([s2, s1], [b, a], {})
        self.assertEqual((pairs["s1"]["terminal_id"], pairs["s2"]["terminal_id"]), ("a", "b"))

    def test_criacao_da_aba_e_comando_sao_um_lancamento_so(self):
        a = tab("a", "/r/loja", "2026-10-31T10:00:00Z", [("2026-10-31T10:00:01Z", "codex")])
        b = tab("b", "/r/loja", "2026-10-31T10:00:02Z", [("2026-10-31T10:00:03Z", "codex")])
        s1 = agent("s1", "/r/loja", "2026-10-31T10:00:04Z", "codex")
        s2 = agent("s2", "/r/loja", "2026-10-31T10:00:05Z", "codex")
        pairs = pairing.resolve([s1, s2], [a, b], {})
        self.assertEqual((pairs["s1"]["terminal_id"], pairs["s2"]["terminal_id"]), ("a", "b"))

    def test_mesma_aba_com_dois_lancamentos(self):
        t = tab("t1", "/r/loja", "2026-10-31T08:00:00Z", [("2026-10-31T10:00:00Z", "codex"), ("2026-10-31T10:00:30Z", "codex")])
        s1 = agent("s1", "/r/loja", "2026-10-31T10:00:02Z", "codex")
        s2 = agent("s2", "/r/loja", "2026-10-31T10:00:32Z", "codex")
        self.assertEqual(set(pairing.resolve([s1, s2], [t], {})), {"s1", "s2"})

    def test_sessao_a_mais_que_lancamentos_fica_sem_par(self):
        t = tab("t1", "/r/loja", "2026-10-31T08:00:00Z", [("2026-10-31T10:00:00Z", "codex")])
        s1 = agent("s1", "/r/loja", "2026-10-31T10:00:02Z", "codex")
        s2 = agent("s2", "/r/loja", "2026-10-31T10:00:04Z", "codex")
        self.assertEqual(set(pairing.resolve([s1, s2], [t], {})), {"s1"})  # a primeira é a que nasce do lançamento

    def test_le_arquivos_de_pareamento(self):
        folder = self.tmp / "pairings"
        folder.mkdir()
        (folder / "s1.json").write_text(json.dumps({"session_id": "s1", "terminal_id": "t1", "theme": "oceano"}))
        (folder / "lixo.json").write_text("{nao")
        self.assertEqual(pairing.read_pairings(folder), {"s1": {"terminal_id": "t1", "theme": "oceano"}})


class HookTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.claude = self.tmp / "claude"
        self.data = self.tmp / "dados"
        self.claude.mkdir()

    def test_instala_com_backup_preserva_o_resto_e_nao_duplica(self):
        original = {"model": "opus", "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo meu"}]}],
                                               "Stop": [{"hooks": [{"type": "command", "command": "say pronto"}]}]}}
        (self.claude / "settings.json").write_text(json.dumps(original, indent=2))
        info = pairing.install_hook(self.claude, self.data, now=1_800_000_000)
        backup = self.claude / "settings.json.vulcan-backup-1800000000"
        self.assertEqual(info["backup"], str(backup))
        self.assertEqual(json.loads(backup.read_text()), original)
        settings = json.loads((self.claude / "settings.json").read_text())
        self.assertEqual(settings["model"], "opus")
        self.assertEqual(settings["hooks"]["Stop"], original["hooks"]["Stop"])
        commands = [h["command"] for e in settings["hooks"]["SessionStart"] for h in e["hooks"]]
        self.assertEqual(commands, ["echo meu", info["script"]])
        pairing.install_hook(self.claude, self.data, now=1_800_000_100)
        again = json.loads((self.claude / "settings.json").read_text())
        self.assertEqual(again, settings)  # segunda vez não duplica

    def test_sem_settings_cria_sem_backup(self):
        info = pairing.install_hook(self.claude, self.data, now=1)
        self.assertIsNone(info["backup"])
        self.assertTrue((self.claude / "settings.json").is_file())

    def run_hook(self, env_extra, stdin):
        info = pairing.install_hook(self.claude, self.data, now=1)
        env = {"PATH": os.environ.get("PATH", ""), **env_extra}
        return subprocess.run([sys.executable, info["script"]], input=stdin, env=env, capture_output=True, text=True, timeout=20)

    def test_script_grava_o_par_so_dentro_de_uma_aba_do_vulcan(self):
        payload = json.dumps({"session_id": "s1", "cwd": "/r/loja", "hook_event_name": "SessionStart"})
        proc = self.run_hook({"VULCAN_SESSION_ID": "t1", "VULCAN_THEME": "oceano"}, payload)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(pairing.read_pairings(self.data / "pairings")["s1"], {"terminal_id": "t1", "theme": "oceano"})
        for env, stdin in (({}, payload), ({"VULCAN_SESSION_ID": "t1"}, "não é json"), ({"VULCAN_SESSION_ID": "t1"}, "{}")):
            with self.subTest(env=env, stdin=stdin):
                (self.data / "pairings" / "s1.json").unlink()
                (self.data / "pairings" / "s1.json").write_text(json.dumps({"session_id": "s1", "terminal_id": "t1"}))
                proc = self.run_hook(env, stdin)
                self.assertEqual(proc.returncode, 0)  # nunca atrapalha o Claude Code
                self.assertEqual(sorted(p.name for p in (self.data / "pairings").iterdir()), ["s1.json"])


class PairingApiTest(test_agents_api.AgentsServerCase):
    def test_sessao_pareada_com_a_aba_pela_pasta_e_horario(self):
        record = self.app.hub.sessions.create("aba000000001", "projeto", None, "/Users/dev/projeto", theme="ardosia")
        session = self.app.agents.index.session(CLAUDE_SID)
        record.created_at = session.started_at[:19] + "Z"  # aba aberta no segundo em que a sessão começou
        card = next(s for s in self.get("/api/agents/sessions")["sessions"] if s["id"] == CLAUDE_SID)
        self.assertEqual((card["pairing_id"], card["theme"]), ("aba000000001", "ardosia"))
        paired = self.get("/api/agents/paired?terminal=aba000000001")
        self.assertEqual(paired["session"]["id"], CLAUDE_SID)
        self.assertIsNone(self.get("/api/agents/paired?terminal=aba000000099")["session"])
        prompts = self.get("/api/prompts?terminal=aba000000001")
        self.assertEqual(prompts["session"]["id"], CLAUDE_SID)


class InstallCommandTest(TempDirTestCase):
    def test_opcao_instalar_hook(self):
        import io
        from contextlib import redirect_stdout
        from unittest import mock
        from vulcan_terminal.__main__ import main
        env = {"CLAUDE_CONFIG_DIR": str(self.tmp / "claude"), "VULCAN_TERMINAL_HOME": str(self.tmp / "dados")}
        out = io.StringIO()
        with mock.patch.dict(os.environ, env), redirect_stdout(out):
            self.assertEqual(main(["--instalar-hook"]), 0)
        info = json.loads(out.getvalue())
        self.assertTrue(info["ok"])
        self.assertTrue(info["script"].startswith(str(self.tmp / "dados")))
        settings = json.loads((self.tmp / "claude" / "settings.json").read_text())
        self.assertEqual(settings["hooks"]["SessionStart"][0]["hooks"][0]["command"], info["script"])


class HookComEspacoTest(TempDirTestCase):
    """No macOS a pasta de dados tem espaço (Application Support)."""

    def setUp(self):
        super().setUp()
        self.claude = self.tmp / "claude"
        self.data = self.tmp / "Application Support" / "VulcanTerminal"

    def command(self):
        settings = json.loads((self.claude / "settings.json").read_text())
        commands = [h["command"] for e in settings["hooks"]["SessionStart"] for h in e["hooks"]]
        self.assertEqual(len(commands), 1, commands)
        return commands[0]

    def test_comando_gravado_roda_pelo_shell(self):
        pairing.install_hook(self.claude, self.data, now=1)
        payload = json.dumps({"session_id": "s1", "cwd": "/r/loja"})
        env = {"PATH": os.environ.get("PATH", ""), "VULCAN_SESSION_ID": "t1", "VULCAN_THEME": "oceano"}
        proc = subprocess.run(["/bin/sh", "-c", self.command()], input=payload, env=env,
                              capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(pairing.read_pairings(self.data / "pairings")["s1"], {"terminal_id": "t1", "theme": "oceano"})

    def test_reinstalar_troca_a_entrada_antiga_sem_aspas(self):
        script = self.data / "hooks" / pairing.SCRIPT_NAME
        self.claude.mkdir(parents=True)
        original = {"model": "opus", "hooks": {"SessionStart": [
            {"hooks": [{"type": "command", "command": str(script)}]}]}}
        (self.claude / "settings.json").write_text(json.dumps(original))
        pairing.install_hook(self.claude, self.data, now=2)
        self.assertNotEqual(self.command(), str(script))
        self.assertIn("'", self.command())
        settings = json.loads((self.claude / "settings.json").read_text())
        self.assertEqual(settings["model"], "opus")
        pairing.install_hook(self.claude, self.data, now=3)
        self.command()  # continua uma entrada só
