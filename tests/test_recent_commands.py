"""Últimos comandos do site, das sessões registradas, para reexecutar."""

from tests.server_helpers import ServerTestCase
from vulcan_celox.core.quick_commands import recent_commands
from vulcan_celox.core.sessions import SessionRecord


def rec(rid, site, cmds):
    return SessionRecord(id=rid, site=site, commands=[{"ts": ts, "cmd": c} for ts, c in cmds])


class RecentTest(ServerTestCase):
    def test_junta_ordena_e_tira_repetidos_seguidos(self):
        records = [
            rec("a", "loja", [("2026-10-31T10:00:00Z", "git status"), ("2026-10-31T10:05:00Z", "php artisan test"),
                              ("2026-10-31T10:06:00Z", "php artisan test")]),
            rec("b", "loja", [("2026-10-31T10:03:00Z", "composer install"), ("2026-10-31T10:07:00Z", "  ")]),
            rec("c", "blog", [("2026-10-31T10:08:00Z", "npm run dev")]),
        ]
        self.assertEqual(recent_commands(records, "loja", 20),
                         [{"command": "php artisan test", "at": "2026-10-31T10:06:00Z"},
                          {"command": "composer install", "at": "2026-10-31T10:03:00Z"},
                          {"command": "git status", "at": "2026-10-31T10:00:00Z"}])
        self.assertEqual(len(recent_commands(records, "loja", 2)), 2)
        self.assertEqual(recent_commands(records, "nenhum", 20), [])

    def test_limite_de_vinte(self):
        records = [rec("a", "loja", [(f"2026-10-31T10:{i:02d}:00Z", f"echo {i}") for i in range(40)])]
        found = recent_commands(records, "loja", 20)
        self.assertEqual(len(found), 20)
        self.assertEqual(found[0]["command"], "echo 39")

    def test_api(self):
        self.app.store.save("sites", {"loja": str(self.tmp)})
        r = self.app.hub.sessions.create("aba000000001", "loja", "loja", str(self.tmp))
        self.app.hub.sessions.add_commands(r.id, ["php artisan migrate", "git push"])
        data = self.request("GET", "/api/sites/loja/recent")[1]
        self.assertEqual([c["command"] for c in data["commands"]], ["git push", "php artisan migrate"])
        self.assertEqual(self.request("GET", "/api/sites/fantasma/recent")[0], 404)
