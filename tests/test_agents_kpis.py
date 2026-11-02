"""vt-16b C5: KPIs do dia contam o que aconteceu hoje, no fuso local."""

import unittest
from datetime import datetime, timedelta, timezone

from vulcan_terminal.core.agents.model import AgentSession, FileTouch
from vulcan_terminal.server.agents_api import kpis, local_day


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class KpisTest(unittest.TestCase):
    def test_arquivos_editados_hoje_contam_pela_data_de_cada_arquivo(self):
        now = datetime.now().astimezone()
        today = now.date().isoformat()
        old = now - timedelta(days=6)
        big = AgentSession(id="a", agent="claude", file_path="/x", last_activity_at=iso(now),
                           files=[FileTouch(f"/r/f{i}.php", "edit", iso(old), iso(old)) for i in range(40)]
                           + [FileTouch("/r/hoje.php", "edit", iso(now), iso(now)), FileTouch("/r/lido.php", "read", iso(now), iso(now))])
        other = AgentSession(id="b", agent="codex", file_path="/y", last_activity_at=iso(old),
                             files=[FileTouch("/r/velho.php", "new", iso(old), iso(old))])
        k = kpis([big, other], today)
        self.assertEqual(k["files_edited_today"], 1)
        self.assertEqual(k["sessions_today"], 1)

    def test_dia_local_usa_o_fuso_da_maquina(self):
        moment = datetime(2026, 10, 31, 1, 30, tzinfo=timezone.utc)
        self.assertEqual(local_day(iso(moment)), moment.astimezone().date().isoformat())
        self.assertIsNone(local_day("ontem"))


if __name__ == "__main__":
    unittest.main()
