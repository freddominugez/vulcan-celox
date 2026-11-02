"""vt-22 C1: uso por turno no índice (tabela agent_usage)."""

import shutil
import sqlite3

from tests.helpers import FIXTURES, TempDirTestCase
from vulcan_terminal.core.agents.index import SCHEMA_VERSION, USAGE_FIELDS, AgentIndex
from vulcan_terminal.core.agents.reading import read_session

USO = FIXTURES / "agents" / "usage"
CLAUDE = USO / "claude-uso.jsonl"
CODEX_SID = "019a1111-2222-7333-8444-555555555555"
CODEX = USO / f"rollout-2026-10-30T20-00-00-{CODEX_SID}.jsonl"
SESSAO_GRANDE = FIXTURES / "agents" / "claude" / "projects" / "-Users-dev-projeto" / \
    "11111111-2222-4333-8444-555555555555.jsonl"


def rows_by_key(rows):
    out = {}
    for r in rows:  # a mesma chave regravada: vale a última, como no upsert do índice
        out[r["key"]] = r
    return out


class ClaudeUsageTest(TempDirTestCase):
    def test_uma_linha_por_message_id_e_sem_synthetic(self):
        rows = rows_by_key(read_session("claude", CLAUDE).usage)
        self.assertEqual(sorted(rows), ["msg_A", "msg_B", "msg_C"])
        a = rows["msg_A"]
        self.assertEqual((a["input"], a["output"], a["cache_read"], a["cache_write_5m"], a["cache_write_1h"],
                          a["reasoning"]), (2, 250, 1000, 1000, 4000, 30))
        self.assertEqual(a["at"], "2026-10-30T12:00:05.000Z")
        self.assertEqual(a["model"], "claude-opus-5-5")
        # sem a divisão 5m/1h, a escrita de cache conta como 5m
        self.assertEqual((rows["msg_B"]["cache_write_5m"], rows["msg_B"]["cache_write_1h"]), (700, 0))
        self.assertEqual(rows["msg_C"]["model"], "claude-sonnet-5-5")

    def test_soma_bate_com_o_total_da_sessao(self):
        for path in (CLAUDE, SESSAO_GRANDE):
            res = read_session("claude", path)
            rows = rows_by_key(res.usage).values()
            t = res.session.tokens
            self.assertEqual(sum(r["input"] for r in rows), t["input"], path.name)
            self.assertEqual(sum(r["output"] for r in rows), t["output"], path.name)
            self.assertEqual(sum(r["cache_read"] for r in rows), t["cache_read"], path.name)
            self.assertEqual(sum(r["cache_write_5m"] + r["cache_write_1h"] for r in rows), t["cache_write"], path.name)

    def test_leitura_em_partes_regrava_o_turno_aberto(self):
        data = CLAUDE.read_bytes()
        cut = data.index(b"\n", data.index(b"msg_A")) + 1  # só a primeira linha de msg_A
        part = self.tmp / "s.jsonl"
        part.write_bytes(data[:cut])
        first = read_session("claude", part)
        self.assertEqual(rows_by_key(first.usage)["msg_A"]["output"], 100)
        part.write_bytes(data)
        second = read_session("claude", part, first.session, first.state, first.offset)
        rows = rows_by_key(second.usage)
        self.assertEqual(rows["msg_A"]["output"], 250)
        self.assertEqual(rows["msg_A"]["at"], "2026-10-30T12:00:05.000Z")


class CodexUsageTest(TempDirTestCase):
    def test_diferencas_do_total_acumulado(self):
        rows = read_session("codex", CODEX).usage
        got = [(r["input"], r["cache_read"], r["output"], r["reasoning"], r["cache_write_5m"]) for r in rows]
        self.assertEqual(got, [
            (20513 - 12032, 12032, 144, 0, 0),                          # primeiro total
            ((41246 - 32512) - (20513 - 12032), 32512 - 12032, 100, 11, 0),  # o total repetido não gera linha
            (5000 - 1000, 1000, 80, 5, 0),                              # total menor: retomada, recomeça a conta
            ((9000 - 4000) - (5000 - 1000), 3000, 40, 4, 200),
        ])
        self.assertEqual({r["model"] for r in rows}, {"gpt-5.5-codex"})
        self.assertEqual(len({r["key"] for r in rows}), 4)

    def test_soma_bate_sem_retomada(self):
        lines = CODEX.read_text().splitlines()[:6]
        path = self.tmp / f"rollout-x-{CODEX_SID}.jsonl"
        path.write_text("\n".join(lines) + "\n")
        res = read_session("codex", path)
        t = res.session.tokens
        self.assertEqual(sum(r["input"] for r in res.usage), t["input"])
        self.assertEqual(sum(r["cache_read"] for r in res.usage), t["cache_read"])
        self.assertEqual(sum(r["output"] for r in res.usage), t["output"])


class IndexUsageTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        shutil.copy(CLAUDE, self.tmp / "c.jsonl")
        shutil.copy(CODEX, self.tmp / CODEX.name)
        self.db = self.tmp / "dados" / "agentes.db"

    def test_indice_grava_e_regrava_sem_duplicar(self):
        index = AgentIndex(self.db)
        try:
            index.update_file("claude", self.tmp / "c.jsonl")
            index.update_file("codex", self.tmp / CODEX.name)
            rows = index.usage_rows()
            self.assertEqual(len(rows), 7)
            self.assertEqual({r["agent"] for r in rows}, {"claude", "codex"})
            with open(self.tmp / "c.jsonl", "a") as fh:
                fh.write('{"type":"user","timestamp":"2026-10-31T09:05:00.000Z","message":{"role":"user","content":"x"}}\n')
            index.update_file("claude", self.tmp / "c.jsonl")
            self.assertEqual(len(index.usage_rows()), 7)
            self.assertEqual(len(index.usage_rows(since="2026-10-31T00:00:00")), 1)
            for r in rows:
                self.assertTrue(all(isinstance(r[k], int) for k in USAGE_FIELDS))
            self.assertEqual(rows[0]["project"], "loja")
        finally:
            index.close()

    def test_esquema_3_reconstroi(self):
        index = AgentIndex(self.db)
        index.update_file("claude", self.tmp / "c.jsonl")
        index.db.execute("DELETE FROM agent_usage")
        index.db.execute("UPDATE meta SET value = '3' WHERE key = 'schema_version'")
        index.db.commit()
        index.close()
        index = AgentIndex(self.db)
        try:
            version = index.db.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0]
            self.assertEqual((version, SCHEMA_VERSION), ("5", 5))
            self.assertEqual(index.db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0)
            index.update_file("claude", self.tmp / "c.jsonl")
            self.assertEqual(len(index.usage_rows()), 3)
        finally:
            index.close()

    def test_esquecer_a_sessao_leva_o_uso(self):
        index = AgentIndex(self.db)
        try:
            sid = index.update_file("claude", self.tmp / "c.jsonl")
            with index.db:
                index._forget(sid)
            self.assertEqual(index.usage_rows(), [])
        finally:
            index.close()
