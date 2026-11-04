"""Agent session routes."""

import json
import shutil
from datetime import datetime, timezone

from tests.helpers import FIXTURES
from tests.server_helpers import ServerTestCase

CLAUDE_SID = "11111111-2222-4333-8444-555555555555"
CODEX_SID = "019a0000-1111-7222-8333-444444444444"
LOOP_SID = "22222222-3333-4444-8555-666666666666"


def loop_session(path):
    lines = [{"type": "user", "timestamp": "2026-10-30T10:00:00Z", "cwd": "/Users/dev/loja", "gitBranch": "fix/frete",
              "message": {"role": "user", "content": "corrija o frete"}}]
    for i in range(6):
        lines.append({"type": "assistant", "timestamp": f"2026-10-30T10:0{i + 1}:00Z", "cwd": "/Users/dev/loja", "message": {
            "id": f"m{i}", "model": "claude-opus-5-5", "usage": {"input_tokens": 1, "output_tokens": 1}, "content": [
                {"type": "tool_use", "name": "Edit", "input": {"file_path": "/Users/dev/loja/app/Frete.php"}},
                {"type": "tool_use", "name": "Bash", "input": {"command": "php artisan test --filter=Frete"}}]}})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(o) + "\n" for o in lines), encoding="utf-8")


class AgentsServerCase(ServerTestCase):
    """Server with the agent fixtures and a looping session; no tests of its own."""

    def env(self):
        claude, codex = self.tmp / "claude", self.tmp / "codex"
        if not claude.exists():
            shutil.copytree(FIXTURES / "agents" / "claude", claude)
            shutil.copytree(FIXTURES / "agents" / "codex", codex)
            loop_session(claude / "projects" / "-Users-dev-loja" / f"{LOOP_SID}.jsonl")
        return {**super().env(), "CLAUDE_CONFIG_DIR": str(claude), "CODEX_HOME": str(codex), "VULCAN_AGENTS": "0"}

    def setUp(self):
        super().setUp()
        self.app.agents.refresh()

    def get(self, path):
        status, data, _ = self.request("GET", path)
        self.assertEqual(status, 200, data)
        return data


class AgentsApiTest(AgentsServerCase):

    def test_lista_com_kpis_e_projetos(self):
        data = self.get("/api/agents/sessions")
        self.assertEqual({s["id"] for s in data["sessions"]}, {CLAUDE_SID, CODEX_SID, LOOP_SID})
        self.assertEqual(data["total"], 3)
        self.assertEqual({p["name"] for p in data["projects"]}, {"projeto", "clerk", "loja"})
        self.assertEqual(data["kpis"]["unpublished"], 3)
        self.assertEqual(data["kpis"]["active"], 0)
        first = data["sessions"][0]
        for key in ("agent", "project", "branch", "ask", "headline", "files_edited", "published", "loop", "last_activity_at"):
            self.assertIn(key, first)

    def test_sessao_sem_projeto_nao_entra_no_filtro(self):
        """An empty name in the filter was left selected in place of All projects and showed up as (1)."""
        sem_pasta = self.tmp / "claude" / "projects" / "-vazio"
        sem_pasta.mkdir(parents=True)
        (sem_pasta / "bbbbbbbb-1111-4222-8333-444444444444.jsonl").write_text(
            '{"type": "user", "sessionId": "bbbbbbbb-1111-4222-8333-444444444444", "timestamp": "2026-10-31T01:00:00.000Z", "uuid": "u", '
            '"parentUuid": null, "message": {"role": "user", "content": "oi"}}\n', encoding="utf-8")
        self.app.agents.refresh()
        data = self.get("/api/agents/sessions")
        self.assertIn("bbbbbbbb-1111-4222-8333-444444444444", [x["id"] for x in data["sessions"]])
        self.assertTrue(all(p["name"] for p in data["projects"]), data["projects"])

    def test_filtros(self):
        self.assertEqual([s["id"] for s in self.get("/api/agents/sessions?agent=codex")["sessions"]], [CODEX_SID])
        self.assertEqual([s["id"] for s in self.get("/api/agents/sessions?project=loja")["sessions"]], [LOOP_SID])
        self.assertEqual([s["id"] for s in self.get("/api/agents/sessions?cwd=/Users/dev/clerk")["sessions"]], [CODEX_SID])
        self.assertEqual(self.get("/api/agents/sessions?active=1")["sessions"], [])
        # a fresh copy (new file dates) is not an active session; a new event written now is
        rollout = self.tmp / "codex" / "sessions" / "2026" / "10" / "30" / f"rollout-2026-10-30T21-15-44-{CODEX_SID}.jsonl"
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with rollout.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"timestamp": now, "type": "event_msg", "payload": {"type": "agent_message", "message": "ok"}}) + "\n")
        self.app.agents.refresh()
        self.assertEqual([s["id"] for s in self.get("/api/agents/sessions?active=1")["sessions"]], [CODEX_SID])

    def test_alerta_de_loop(self):
        loop = next(s for s in self.get("/api/agents/sessions")["sessions"] if s["id"] == LOOP_SID)
        self.assertEqual(loop["loop"]["count"], 6)
        self.assertEqual(loop["loop"]["command"], "php artisan test --filter=Frete")
        others = [s for s in self.get("/api/agents/sessions")["sessions"] if s["id"] != LOOP_SID]
        self.assertTrue(all(s["loop"] is None for s in others))

    def test_detalhe_com_eventos_paginados(self):
        data = self.get(f"/api/agents/sessions/{CLAUDE_SID}?limit=20")
        s = data["session"]
        self.assertEqual(len(s["files"]), 13)
        self.assertEqual(len(s["command_list"]), 41)
        self.assertEqual(len(data["events"]), 20)
        self.assertEqual(data["next"], 20)
        page2 = self.get(f"/api/agents/sessions/{CLAUDE_SID}?from=20&limit=20")
        self.assertNotEqual(page2["events"][0], data["events"][0])
        self.assertEqual(set(data["events"][0]), {"at", "kind", "text", "tool"})

    def test_erros(self):
        status, data, _ = self.request("GET", "/api/agents/sessions/nao-existe")
        self.assertEqual(status, 404)
        status, _, _ = self.request("GET", f"/api/agents/sessions/{CLAUDE_SID}?from=x")
        self.assertEqual(status, 400)
        status, _, _ = self.request("GET", "/api/agents/sessions", token=False)
        self.assertEqual(status, 401)

    def test_revisao_muda_quando_o_jsonl_cresce(self):
        rev = self.get("/api/agents/revision")["revision"]
        path = self.tmp / "claude" / "projects" / "-Users-dev-loja" / f"{LOOP_SID}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "timestamp": "2026-10-30T11:00:00Z", "message": {"content": "mais um"}}) + "\n")
        status, data, _ = self.request("POST", "/api/agents/refresh", body={})
        self.assertEqual((status, data["changed"]), (200, [LOOP_SID]))
        self.assertGreater(self.get("/api/agents/revision")["revision"], rev)
