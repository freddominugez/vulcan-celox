"""Sessões do Codex comprimidas (.jsonl.zst). Fixture sintética: o Codex só comprime em manutenção e não há
arquivo real nesta máquina. A maior parte usa um `zstd` falso (cat); um teste usa o de verdade, quando existe."""
import json
import os
import shutil
import subprocess
import unittest
from unittest import mock

from tests.helpers import TempDirTestCase
from vulcan_celox.core.agents import discovery, status
from vulcan_celox.core.agents.index import AgentIndex
from vulcan_celox.core.agents.reading import read_session
from vulcan_celox.core.agents.watcher import AgentWatcher

SID = "019b0000-1111-7222-8333-444444444444"


def rollout_lines():
    rows = [{"timestamp": "2026-10-20T10:00:00Z", "type": "session_meta",
             "payload": {"id": SID, "cwd": "/Users/dev/loja", "cli_version": "0.166.0"}},
            {"timestamp": "2026-10-20T10:00:03Z", "type": "event_msg", "payload": {"type": "user_message", "message": "crie o cupom"}}]
    return "".join(json.dumps(r) + "\n" for r in rows)


class Base(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.sessions = self.tmp / "codex" / "sessions" / "2026" / "10" / "20"
        self.sessions.mkdir(parents=True)
        self.name = f"rollout-2026-10-20T10-00-00-{SID}.jsonl"
        fake = self.tmp / "bin" / "zstd"
        fake.parent.mkdir()
        fake.write_text('#!/bin/sh\n# zstd -dcq -- arquivo\ncase "$3" in *ruim*) echo erro >&2; exit 1;; esac\nexec cat "$3"\n')
        fake.chmod(0o755)
        self.fake = str(fake)

    def write(self, suffix=".zst", name=None):
        path = self.sessions / ((name or self.name) + suffix)
        path.write_text(rollout_lines(), encoding="utf-8")
        return path


class DescobertaTest(Base):
    def test_com_e_sem_zstd(self):
        path = self.write()
        roots = [self.tmp / "codex"]
        self.assertEqual(discovery.codex_session_files(roots), ([], 1))  # sem zstd: ignorado e contado
        self.assertEqual(discovery.codex_session_files(roots, self.fake), ([path], 0))

    def test_copia_em_jsonl_vence_a_comprimida(self):
        plain = self.write("")
        self.write()
        self.assertEqual(discovery.codex_session_files([self.tmp / "codex"], self.fake), ([plain], 0))

    def test_achar_o_zstd(self):
        self.assertEqual(discovery.zstd_bin({"VULCAN_ZSTD_BIN": self.fake}), self.fake)
        self.assertIsNone(discovery.zstd_bin({"VULCAN_ZSTD_BIN": ""}))
        self.assertIsNone(discovery.zstd_bin({"VULCAN_ZSTD_BIN": str(self.tmp / "nada")}))
        self.assertIsNone(discovery.zstd_bin({"PATH": str(self.tmp / "vazio")}, extra=()))
        self.assertEqual(discovery.zstd_bin({"PATH": str(self.tmp / "vazio")}, extra=(self.fake,)), self.fake)
        self.assertEqual(discovery.zstd_bin({"PATH": str(self.tmp / "bin")}, extra=()), self.fake)

    def test_doctor_diz_o_modo(self):
        self.write()
        env = {"CLAUDE_CONFIG_DIR": str(self.tmp / "claude"), "CODEX_HOME": str(self.tmp / "codex")}
        info = status.collect({**env, "VULCAN_ZSTD_BIN": self.fake})
        self.assertEqual((info["codex_session_files"], info["codex_zst_ignored"], info["codex_zst_reader"]), (1, 0, self.fake))
        info = status.collect({**env, "VULCAN_ZSTD_BIN": ""})
        self.assertEqual((info["codex_session_files"], info["codex_zst_ignored"], info["codex_zst_reader"]), (0, 1, None))


class LeituraTest(Base):
    def test_le_em_stream(self):
        with mock.patch.dict(os.environ, {"VULCAN_ZSTD_BIN": self.fake}):
            res = read_session("codex", self.write())
        self.assertEqual((res.session.id, res.session.cwd), (SID, "/Users/dev/loja"))
        self.assertEqual(res.session.first_user_message, "crie o cupom")
        self.assertEqual(res.errors, [])
        self.assertGreater(res.offset, 0)

    def test_id_pelo_nome_do_arquivo_quando_nao_ha_meta(self):
        self.assertEqual(read_session.__globals__["_readers"]()["codex"][0](self.sessions / (self.name + ".zst")).id, SID)

    def test_corrompido_vira_erro_sem_derrubar(self):
        with mock.patch.dict(os.environ, {"VULCAN_ZSTD_BIN": self.fake}):
            res = read_session("codex", self.write(name=f"ruim-{SID}.jsonl"))
        self.assertEqual(res.session.id, SID)
        self.assertEqual(len(res.errors), 1)
        self.assertIn("zstd", res.errors[0][1])

    def test_sem_zstd_na_hora_de_ler_vira_erro(self):
        with mock.patch.dict(os.environ, {"VULCAN_ZSTD_BIN": ""}):
            res = read_session("codex", self.write())
        self.assertEqual(len(res.errors), 1)
        self.assertIn("zstd", res.errors[0][1])

    @unittest.skipUnless(shutil.which("zstd"), "zstd ausente")
    def test_zstd_de_verdade(self):
        plain = self.write("")
        subprocess.run(["zstd", "-q", "--rm", str(plain)], check=True)
        path = self.sessions / (self.name + ".zst")
        self.assertTrue(path.is_file())
        with mock.patch.dict(os.environ, {"VULCAN_ZSTD_BIN": shutil.which("zstd")}):
            res = read_session("codex", path)
        self.assertEqual((res.session.id, res.session.first_user_message, res.errors), (SID, "crie o cupom", []))


class IndiceTest(Base):
    def setUp(self):
        super().setUp()
        self.index = AgentIndex(self.tmp / "agentes.db")
        self.addCleanup(self.index.close)
        self.env = {"CLAUDE_CONFIG_DIR": str(self.tmp / "claude"), "CODEX_HOME": str(self.tmp / "codex"), "VULCAN_ZSTD_BIN": self.fake}
        patcher = mock.patch.dict(os.environ, {"VULCAN_ZSTD_BIN": self.fake})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_jsonl_que_vira_zst_continua_uma_sessao_so(self):
        plain = self.write("")
        AgentWatcher(self.index, self.env).run_once()
        self.assertEqual([s.id for s in self.index.sessions()], [SID])
        comp = self.write()
        os.rename(plain, str(plain) + ".movido")  # o Codex comprime e tira o .jsonl
        AgentWatcher(self.index, self.env).run_once()
        found = self.index.sessions()
        self.assertEqual([s.id for s in found], [SID])
        self.assertEqual(found[0].file_path, str(comp))

    def test_reler_a_comprimida_nao_duplica(self):
        path = self.write()
        self.assertEqual(self.index.update_file("codex", path), SID)
        before = len(self.index.search("cupom"))
        self.assertIsNone(self.index.update_file("codex", path))  # nada mudou
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n")  # arquivo trocado: relê do início, sem somar eventos
        self.assertEqual(self.index.update_file("codex", path), SID)
        self.assertEqual(len(self.index.search("cupom")), before)
