import json
from pathlib import Path

from tests.server_helpers import ServerTestCase
from vulcan_celox.core.backup import PENDING_DIR
from vulcan_celox.core.memory_mask import mask_saved_memories
from vulcan_celox.core.session_memory import SESSIONS_DIR


class DataApiTest(ServerTestCase):
    def test_backup_grava_preferencia_e_prepara_restauro(self):
        folder = self.tmp / "bk"
        status, data = self.request("POST", "/api/data/backup", {"folder": str(folder)})[:2]
        self.assertEqual(status, 200)
        self.assertTrue(Path(data["created"]["path"]).is_file())
        self.assertEqual(self.request("GET", "/api/data/backup")[1]["folder"], str(folder))
        self.assertFalse(data["restore_pending"])
        status, data = self.request("POST", "/api/data/restore", {"path": data["created"]["path"]})[:2]
        self.assertEqual(status, 200)
        self.assertTrue(data["restore_pending"])
        self.assertTrue((Path(self.app.data_dir) / PENDING_DIR).is_dir())

    def test_recusas(self):
        self.assertEqual(self.request("POST", "/api/data/backup", {"folder": ""})[0], 400)
        self.assertEqual(self.request("POST", "/api/data/backup", {"folder": str(self.app.data_dir)})[0], 400)
        self.assertEqual(self.request("POST", "/api/data/restore", {"path": str(self.tmp / "nada.zip")})[0], 400)
        self.assertEqual(self.request("POST", "/api/data/restore", {"path": "x"}, token=False)[0], 401)

    def test_mascara_o_que_ja_estava_gravado(self):
        folder = Path(self.app.data_dir) / SESSIONS_DIR / "global"
        folder.mkdir(parents=True, exist_ok=True)
        old = folder / "velha.md"
        old.write_text("DB_PASSWORD=senha-antiga\nnada aqui", encoding="utf-8")
        clean = folder / "limpa.md"
        clean.write_text("sem nada", encoding="utf-8")
        before = clean.stat().st_mtime_ns
        record = self.app.hub.sessions.create("s1", "t", None, "/tmp", None)
        record.commands.append({"ts": "2026-01-01T00:00:00Z", "cmd": "mysql -usr -psenha-digitada"})
        status, data = self.request("POST", "/api/data/mask-saved", {})[:2]
        self.assertEqual(status, 200)
        self.assertEqual(data["commands"], 1)
        self.assertEqual(data["files"], 1)
        self.assertEqual(data["secrets"], 1)
        self.assertNotIn("senha-antiga", old.read_text(encoding="utf-8"))
        self.assertEqual(clean.stat().st_mtime_ns, before)
        self.assertNotIn("senha-digitada", json.dumps([r.to_dict() for r in self.app.hub.sessions.list()]))
        self.assertEqual(mask_saved_memories(self.app.data_dir), (0, 0))  # a second run finds nothing


class RestoresApiTest(ServerTestCase):
    def setUp(self):
        super().setUp()
        aside = Path(self.app.data_dir) / ".restauros"
        self.copy = aside / "20261105-101500"
        self.copy.mkdir(parents=True)
        (self.copy / "tasks.json").write_text("antigo", encoding="utf-8")
        (aside / "solto.txt").write_text("x", encoding="utf-8")
        self.outside = self.tmp / "fora"
        self.outside.mkdir()
        (self.outside / "importante.txt").write_text("x", encoding="utf-8")
        (aside / "20261105-101501").symlink_to(self.outside)

    def test_lista_so_copias_de_verdade(self):
        status, data = self.request("GET", "/api/data/restores")[:2]
        self.assertEqual(status, 200)
        self.assertEqual([r["name"] for r in data["restores"]], ["20261105-101500"])
        self.assertEqual(data["restores"][0]["size"], len("antigo"))

    def test_recusas_sem_tocar_em_nada(self):
        for name in ("../..", "20261105-101500/..", "..", "20991231-000000", "20261105-101501", "solto.txt", 3, None):
            with self.subTest(name=name):
                self.assertEqual(self.request("POST", "/api/data/restores/trash", {"name": name})[0], 400)
        self.assertTrue((self.outside / "importante.txt").is_file())
        self.assertTrue(self.copy.is_dir())
        self.assertEqual(self.fake.calls, [])

    def test_vai_para_a_lixeira_e_nada_e_apagado(self):
        status, data = self.request("POST", "/api/data/restores/trash", {"name": "20261105-101500"})[:2]
        self.assertEqual(status, 200)
        self.assertEqual(data["restores"], [])
        self.assertTrue(any("osascript" in c.argv[0] or "gio" in c.argv[0] for c in self.fake.calls))
        # the fake Trash does nothing: the folder ends up in the app's own trash folder, whole
        kept = list((Path(self.app.data_dir) / "lixeira").glob("*-20261105-101500/tasks.json"))
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].read_text(encoding="utf-8"), "antigo")


class InspectApiTest(ServerTestCase):
    def test_confere_sem_preparar(self):
        made = self.request("POST", "/api/data/backup", {"folder": str(self.tmp / "bk")})[1]["created"]["path"]
        status, data = self.request("POST", "/api/data/backup/inspect", {"path": made})[:2]
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertIn("counts", data)
        self.assertFalse((Path(self.app.data_dir) / PENDING_DIR).exists())
        self.assertEqual(self.request("POST", "/api/data/backup/inspect", {"path": str(self.tmp / "x.zip")})[0], 400)
        self.assertEqual(self.request("POST", "/api/data/backup/inspect", {"path": ""})[0], 400)


class PendingRestoreOnStartTest(ServerTestCase):
    def test_app_aplica_ao_abrir(self):
        from vulcan_celox.core.backup import create_backup, prepare_restore
        from vulcan_celox.server.app import VulcanApp
        self.app.store.save("marcador", {"v": 1})
        backup = create_backup(self.app.data_dir, self.tmp / "bk", "1")["path"]
        self.app.store.save("marcador", {"v": 2})
        prepare_restore(backup, self.app.data_dir)
        runner = self.app.runner
        self.app.shutdown()  # as when reopening: the previous app no longer holds the files
        self.app = VulcanApp(env=self.env(), runner=runner, token=self.token)
        self.app.start()  # tearDown closes this one
        self.assertEqual(self.app.store.load("marcador", {}), {"v": 1})
