"""Sessão agrupada por pedido, nos dois agentes. Fixtures sintéticas."""

import json

from tests.test_agents_api import AgentsServerCase
from tests.test_agent_edits import PATCH, codex_call, codex_meta, codex_user, tool_result, tool_use

SID = "aaaaaaaa-5555-4666-8777-888888888888"
CODEX = "77777777-8888-4999-8aaa-bbbbbbbbbbbb"


def user(text):
    return {"type": "user", "timestamp": "2026-11-02T10:00:00Z", "cwd": "/sintetico/projeto", "message": {"role": "user", "content": text}}


def bash(tool_id, command):
    return tool_use(tool_id, "Bash", command=command)


class TurnsApiTest(AgentsServerCase):
    def write(self, *lines):
        path = self.tmp / "claude" / "projects" / "-sintetico" / f"{SID}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
        self.app.agents.refresh()

    def turns(self, query="", sid=SID):
        return self.get(f"/api/agents/sessions/{sid}/turns{query}")

    def test_agrupa_por_pedido(self):
        self.write(user("primeiro"), tool_use("t1", "Edit", file_path="/sintetico/projeto/a.py", old_string="x", new_string="y"),
                   tool_result("t1"), bash("t2", "pytest"), user("segundo"), tool_use("t3", "Read", file_path="/sintetico/projeto/b.py"))
        data = self.turns()
        self.assertEqual((data["total"], data["next"]), (2, None))
        um, dois = data["turns"]
        self.assertEqual((um["turn"], um["ask"], um["edits"], um["commands_total"]), (1, "primeiro", 1, 1))
        self.assertEqual(um["files"], [{"path": "/sintetico/projeto/a.py", "kind": "edit", "seq": 1}])
        self.assertEqual(um["commands"][0]["text"], "pytest")
        self.assertEqual(um["commands"][0]["kind"], "test")
        self.assertEqual(dois["files"], [{"path": "/sintetico/projeto/b.py", "kind": "read", "seq": None}])

    def test_edicao_falha_nao_leva_ao_diff(self):
        self.write(user("x"), tool_use("t1", "Edit", file_path="/p/a.py", old_string="x", new_string="y"), tool_result("t1", error=True))
        self.assertIsNone(self.turns()["turns"][0]["files"][0]["seq"])

    def test_paginacao(self):
        self.write(*[user(f"pedido {i}") for i in range(5)])
        first = self.turns("?limit=2")
        self.assertEqual([t["turn"] for t in first["turns"]], [1, 2])
        self.assertEqual(first["next"], 2)
        rest = self.turns(f"?start={first['next']}&limit=10")
        self.assertEqual([t["turn"] for t in rest["turns"]], [3, 4, 5])
        self.assertIsNone(rest["next"])
        self.assertEqual(self.request("GET", f"/api/agents/sessions/{SID}/turns?limit=abc")[0], 400)

    def test_sessao_sem_pedido(self):
        self.write(tool_use("t1", "Edit", file_path="/p/a.py", old_string="x", new_string="y"))
        data = self.turns()
        self.assertEqual(data["turns"][0]["turn"], 0)
        self.assertEqual(data["turns"][0]["ask"], "")

    def test_sessao_vazia(self):
        self.write({"type": "system", "subtype": "x", "timestamp": "2026-11-02T10:00:00Z"}, user(" "))
        status, data, _ = self.request("GET", f"/api/agents/sessions/{SID}/turns")
        self.assertEqual((status, data["turns"], data["total"]), (200, [], 0))

    def test_sessao_desconhecida(self):
        self.assertEqual(self.request("GET", "/api/agents/sessions/99999999-5555-4666-8777-888888888888/turns")[0], 404)

    def test_codex_com_caminho_relativo_vira_absoluto(self):
        path = self.tmp / "codex" / "sessions" / f"rollout-2026-11-02T10-00-00-{CODEX}.jsonl"
        path.write_text("".join(json.dumps(x) + "\n" for x in (codex_meta(), codex_user(), codex_call("apply_patch", PATCH))), encoding="utf-8")
        self.app.agents.refresh()
        turn = self.turns(sid=CODEX)["turns"][0]
        self.assertEqual(turn["ask"], "faça")
        self.assertEqual({f["path"] for f in turn["files"]}, {"/sintetico/projeto/a.py", "/sintetico/projeto/b.py", "/sintetico/projeto/c.py"})
        self.assertTrue(all(f["seq"] for f in turn["files"]))

    def test_pareada_diz_se_o_agente_esta_vivo(self):
        self.assertEqual(self.get("/api/agents/paired?terminal=zzz"), {"session": None, "alive": False})
