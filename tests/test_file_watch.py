"""Live changes of a folder, with real writes in a temporary folder."""

import os
import shutil
import time
import unittest
from urllib.parse import quote

from tests.helpers import TempDirTestCase
from tests.server_helpers import ServerTestCase
from vulcan_celox.core.file_tree import Ignored
from vulcan_celox.core.file_watch import FileWatches, RootWatch, next_interval


def no_ignored(_root):
    return Ignored(set())


class WatchCase(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.root = self.tmp / "p"
        self.root.mkdir()
        self.watch = None

    def tearDown(self):
        if self.watch:
            self.watch.stop()
            self.watch.thread.join(3)
        super().tearDown()

    def open(self, **kw):
        kw.setdefault("low", 0.02)
        kw.setdefault("high", 0.05)
        self.watch = RootWatch(str(self.root), kw.pop("ignored", no_ignored), 1, **kw)
        self.watch.start()
        self.assertTrue(self.watch.ready.wait(5))
        self.cursor = self.watch.poll(None, [], "")["cursor"]
        return self.watch

    def wait_events(self, count=1, timeout=4.0):
        deadline = time.monotonic() + timeout
        got = []
        while time.monotonic() < deadline and len(got) < count:
            data = self.watch.poll(self.cursor, [], "")
            got += data["events"]
            self.cursor = data["cursor"]
            time.sleep(0.02)
        return got

    def changes(self, events):
        return [(e["rel"], e["change"]) for e in events]


class MudancasTest(WatchCase):
    def test_criar_alterar_apagar(self):
        self.open()
        (self.root / "a.txt").touch()
        got = self.wait_events()
        self.assertEqual(self.changes(got), [("a.txt", "added")])
        self.assertEqual((got[0]["kind"], got[0]["agent"]), ("file", None))
        (self.root / "a.txt").write_text("dois longo", encoding="utf-8")
        self.assertEqual(self.changes(self.wait_events()), [("a.txt", "modified")])
        (self.root / "a.txt").unlink()
        # writing truncates and then fills the file: a slow sweep can see two changes, so the deletion may come after one more
        got = self.changes(self.wait_events())
        if got == [("a.txt", "modified")]:
            got = self.changes(self.wait_events())
        self.assertEqual(got, [("a.txt", "deleted")])

    def test_renomear_vira_apagado_e_novo(self):
        (self.root / "a.txt").write_text("um", encoding="utf-8")
        self.open()
        os.rename(self.root / "a.txt", self.root / "b.txt")
        self.assertEqual(sorted(self.changes(self.wait_events(2))), [("a.txt", "deleted"), ("b.txt", "added")])

    def test_mesma_data_com_outro_tamanho(self):
        alvo = self.root / "a.txt"
        alvo.write_text("um", encoding="utf-8")
        info = alvo.stat()
        self.open()
        alvo.write_text("um mais longo", encoding="utf-8")
        os.utime(alvo, ns=(info.st_atime_ns, info.st_mtime_ns))
        self.assertEqual(self.changes(self.wait_events()), [("a.txt", "modified")])

    def test_mesmo_tamanho_com_outra_data(self):
        alvo = self.root / "a.txt"
        alvo.write_text("um", encoding="utf-8")
        self.open()
        alvo.write_text("oi", encoding="utf-8")
        os.utime(alvo, (1000, 1000))
        self.assertEqual(self.changes(self.wait_events()), [("a.txt", "modified")])

    def test_pasta_nova_com_arquivos_e_pasta_apagada(self):
        self.open()
        (self.root / "n" / "m").mkdir(parents=True)
        (self.root / "n" / "m" / "x.py").touch()
        got = self.changes(self.wait_events(3))
        self.assertIn(("n", "added"), got)
        self.assertIn(("n/m/x.py", "added"), got)
        shutil.move(str(self.root / "n"), str(self.tmp / "fora"))
        got = self.changes(self.wait_events(3))
        self.assertIn(("n/m/x.py", "deleted"), got)
        self.assertIn(("n", "deleted"), got)

    def test_nao_segue_link_nem_ve_git(self):
        fora = self.tmp / "fora"
        fora.mkdir()
        (self.root / ".git").mkdir()
        os.symlink(fora, self.root / "atalho")
        self.open()
        (fora / "x").touch()
        (self.root / ".git" / "index").touch()
        (self.root / "marca").touch()
        self.assertEqual(self.changes(self.wait_events()), [("marca", "added")])

    def test_ignorado_so_com_a_pasta_aberta(self):
        (self.root / "node_modules").mkdir()
        watch = self.open(ignored=lambda _r: Ignored(None))
        (self.root / "node_modules" / "a").touch()
        (self.root / "marca").touch()
        self.assertEqual(self.changes(self.wait_events()), [("marca", "added")])
        watch.poll(self.cursor, ["node_modules"], "")
        time.sleep(0.2)
        (self.root / "node_modules" / "b").touch()
        got = self.wait_events_open(["node_modules"])
        self.assertEqual(self.changes(got), [("node_modules/b", "added")])
        self.assertTrue(got[0]["ignored"])

    def wait_events_open(self, opened, timeout=4.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = self.watch.poll(self.cursor, opened, "")
            self.cursor = data["cursor"]
            if data["events"]:
                return data["events"]
            time.sleep(0.02)
        return []

    def test_sensivel_vem_marcado(self):
        self.open()
        (self.root / ".env").write_text("x", encoding="utf-8")
        self.assertTrue(self.wait_events()[0]["sensitive"])

    def test_pasta_que_some(self):
        (self.root / "a.txt").touch()
        self.open()
        shutil.move(str(self.root), str(self.tmp / "levada"))
        deadline = time.monotonic() + 4
        data = {}
        while time.monotonic() < deadline and not data.get("missing"):
            data = self.watch.poll(self.cursor, [], "")
            time.sleep(0.02)
        self.assertTrue(data["missing"])
        self.assertEqual(self.changes(data["events"]), [("a.txt", "deleted")])
        shutil.move(str(self.tmp / "levada"), str(self.root))
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline and data.get("missing"):
            data = self.watch.poll(data["cursor"], [], "")
            time.sleep(0.02)
        self.assertFalse(data["missing"])

    def test_foto_para_a_abertura_rapida(self):
        (self.root / "s").mkdir()
        (self.root / "s" / "a.py").touch()
        (self.root / "b.py").touch()
        self.open()
        self.assertEqual(self.watch.photo_files(), ["b.py", "s/a.py"])


class CursorTest(WatchCase):
    def test_sem_cursor_nao_devolve_eventos(self):
        self.open()
        (self.root / "a").touch()
        self.wait_events()
        data = self.watch.poll(None, [], "")
        self.assertEqual((data["events"], data["reset"]), ([], False))
        self.assertGreater(data["cursor"], 1)

    def test_cursor_antigo_devolve_reset(self):
        self.open()
        with self.watch.lock:
            self.watch.events.extend({"seq": 100 + i, "rel": str(i)} for i in range(2000))
            self.watch.seq = 2099
        self.assertTrue(self.watch.poll(5, [], "")["reset"])
        self.assertTrue(self.watch.poll(99999, [], "")["reset"])
        self.assertFalse(self.watch.poll(99, [], "")["reset"])
        self.assertTrue(self.watch.poll(0, [], "")["reset"], "cursor de antes da foto")

    def test_guarda_so_os_ultimos_2000(self):
        self.open()
        for i in range(2100):
            (self.root / f"f{i}").touch()
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline and self.watch.seq < 2101:
            time.sleep(0.02)
        self.assertEqual(len(self.watch.events), 2000)
        self.assertTrue(self.watch.poll(self.cursor, [], "")["reset"])


class OrcamentoTest(WatchCase):
    def test_acima_do_orcamento_observa_so_o_aberto(self):
        (self.root / "muito").mkdir()
        (self.root / "aberta").mkdir()
        (self.root / "fechada").mkdir()
        for i in range(40):
            (self.root / "muito" / f"f{i}").touch()
        watch = self.open(budget=20)
        self.assertTrue(watch.poll(None, [], "")["partial"])
        (self.root / "fechada" / "a").touch()
        self.assertEqual(self.wait_events_named(["aberta"], 0.4), [])
        (self.root / "aberta" / "b").touch()
        self.assertEqual(self.changes(self.wait_events_named(["aberta"], 4)), [("aberta/b", "added")])

    def wait_events_named(self, opened, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = self.watch.poll(self.cursor, opened, "")
            self.cursor = data["cursor"]
            if data["events"]:
                return data["events"]
            time.sleep(0.02)
        return []

    def test_arquivo_aberto_em_pasta_recolhida(self):
        (self.root / "s").mkdir()
        for i in range(30):
            (self.root / f"f{i}").touch()
        (self.root / "s" / "a.txt").touch()
        self.open(budget=10)
        self.watch.poll(self.cursor, [], "s/a.txt")
        time.sleep(0.2)
        (self.root / "s" / "a.txt").write_text("mudou", encoding="utf-8")
        deadline = time.monotonic() + 4
        got = []
        while time.monotonic() < deadline and not got:
            data = self.watch.poll(self.cursor, [], "s/a.txt")
            got = data["events"]
            self.cursor = data["cursor"]
            time.sleep(0.02)
        self.assertEqual(self.changes(got), [("s/a.txt", "modified")])


class ParadaTest(TempDirTestCase):
    def test_intervalo(self):
        self.assertEqual(next_interval(0.01), 1.0)
        self.assertEqual(next_interval(0.5), 5.0)
        self.assertEqual(next_interval(30), 15.0)

    def test_para_sem_consulta_e_o_cursor_antigo_recarrega(self):
        root = self.tmp / "p"
        root.mkdir()
        watches = FileWatches(no_ignored, idle=0.15, low=0.02, high=0.05)
        real = str(root)
        cursor = watches.poll(real, None, [], "")["cursor"]
        first = watches.watches[real]
        first.thread.join(3)
        self.assertFalse(first.thread.is_alive(), "a thread não parou")
        self.assertNotIn(real, watches.watches)
        data = watches.poll(real, cursor, [], "")
        self.assertTrue(data["reset"])
        watches.stop()

    def test_uma_thread_por_raiz(self):
        root = self.tmp / "p"
        root.mkdir()
        watches = FileWatches(no_ignored, low=0.02, high=0.05)
        watches.poll(str(root), None, [], "")
        watch = watches.watches[str(root)]
        watches.poll(str(root), None, [], "")
        self.assertIs(watches.watches[str(root)], watch)
        watches.stop()
        watch.thread.join(3)
        self.assertFalse(watch.thread.is_alive())


class CpuTest(TempDirTestCase):
    def test_vinte_mil_arquivos_abaixo_de_10_por_cento(self):
        """Budget of the contract, with the real intervals and the real ignored check."""
        from vulcan_celox.core.file_tree import IgnoreCache
        root = self.tmp / "grande"
        for d in range(20):
            (root / f"d{d}").mkdir(parents=True)
            for i in range(999):
                (root / f"d{d}" / f"f{i}.txt").touch()
        watches = FileWatches(IgnoreCache().get)
        watches.poll(str(root), None, [], "")
        watch = watches.watches[str(root)]
        self.assertFalse(watch.partial)
        start_cpu, start_wall = time.process_time(), time.monotonic()
        while time.monotonic() - start_wall < 8:
            watch.poll(None, [], "")
            time.sleep(1)
        share = (time.process_time() - start_cpu) / (time.monotonic() - start_wall)
        watches.stop()
        watch.thread.join(3)
        self.assertLess(share, 0.10, f"média de {share:.1%} de um núcleo")


class RotaTest(ServerTestCase):
    def test_rota_changes(self):
        project = self.tmp / "proj"
        project.mkdir()
        root = str(project.resolve())
        self.request("POST", "/api/files/roots", body={"path": root})
        cursor = self.request("GET", f"/api/files/changes?root={quote(root)}")[1]["cursor"]
        (project / "novo.txt").touch()
        deadline = time.monotonic() + 5
        events = []
        while time.monotonic() < deadline and not events:
            data = self.request("GET", f"/api/files/changes?root={quote(root)}&since={cursor}&open=a&open=../x&file=")[1]
            events, cursor = data["events"], data["cursor"]
            time.sleep(0.1)
        self.assertEqual([(e["rel"], e["change"], e["agent"]) for e in events], [("novo.txt", "added", None)])
        self.assertEqual(self.request("GET", f"/api/files/changes?root={quote(root)}&since=x")[0], 400)
        self.assertEqual(self.request("GET", f"/api/files/changes?root={quote(root)}&file=../x")[0], 400)
        self.assertEqual(self.request("GET", "/api/files/changes?root=/")[0], 403)


if __name__ == "__main__":
    unittest.main()
